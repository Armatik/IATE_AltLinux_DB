#!/usr/bin/env python3
# populate_db.py

import subprocess
import random
import argparse
import logging
import re
from datetime import datetime, timedelta
from collections import defaultdict

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import IntegrityError

from models import (
    Base,
    Package,
    Maintainer,
    ACL,
    PackageArchitecture,
    PackageUpdate,
    PackageGroup,
    Report
)

# --- Logging setup ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger(__name__)

# Static RPM groups list (you can extend this list as needed)
RPM_GROUPS = [
    "Accessibility", "Archiving/Backup", "Archiving/Cd burning", # ...
    "Video"
]

# Pool of short descriptions for bug reports
SUMMARY_OPTIONS = [
    "Application crashes on startup",
    "Settings are not saved",
    "Memory leak in background task",
    "UI alignment is broken",
    "Installation fails with error code 123",
    "Unexpected logout after inactivity",
    "File export generates corrupt archive",
    "Search returns no results",
    "Slow performance on large datasets",
    "Notifications do not appear",
    "Theme colors not applied",
    "Error dialog shows empty message",
    "Keyboard shortcuts stop working",
    "Configuration page fails to load",
    "Data import hangs indefinitely"
]

def parse_rpm_name(rpm_full_name):
    """Split 'name-version-release.arch' into (name, version-release, arch)."""
    try:
        nevra, arch = rpm_full_name.rsplit('.', 1)
    except ValueError:
        nevra, arch = rpm_full_name, ''
    parts = nevra.rsplit('-', 2)
    if len(parts) == 3:
        name, ver, rel = parts
        ver_rel = f"{ver}-{rel}"
    else:
        name = nevra
        ver_rel = ""
    return name, ver_rel, arch

def parse_rpm_info(name):
    """Run `rpm -qi name` and extract fields."""
    data = {}
    try:
        info = subprocess.check_output(
            ['rpm', '-qi', name],
            text=True,
            stderr=subprocess.DEVNULL
        )
    except subprocess.CalledProcessError:
        return data

    for line in info.splitlines():
        if ':' not in line:
            continue
        key, val = [p.strip() for p in line.split(':', 1)]
        if key == 'Version':
            data['version'] = val
        elif key == 'Release':
            data['release'] = val
        elif key == 'Architecture':
            data['arch'] = val
        elif key == 'Group':
            data['group'] = val
        elif key == 'Packager':
            # 'Name <nick@domain>'
            if '<' in val and '>' in val:
                full, rest = val.split('<', 1)
                nick = rest.split('@', 1)[0]
                data['packager_full'] = full.strip()
                data['packager_nick'] = nick.strip()
            else:
                data['packager_full'] = val
                data['packager_nick'] = val.split()[0]
        elif key == 'Summary':
            data['summary'] = val
    return data

def random_dates(count, min_days, max_days):
    """Generate sorted list of `count` datetimes between now-max_days and now-min_days."""
    now = datetime.now()
    dates = []
    for _ in range(count):
        days_ago = random.randint(min_days, max_days)
        dt = now - timedelta(days=days_ago,
                             hours=random.randint(0,23),
                             minutes=random.randint(0,59))
        dates.append(dt)
    return sorted(dates)

def bump_version_release(ver_rel, idx):
    """Increment the final numeric component of version and release by idx."""
    if '-' in ver_rel:
        ver, rel = ver_rel.split('-',1)
    else:
        ver, rel = ver_rel, ''
    parts = ver.split('.')
    try:
        parts[-1] = str(int(parts[-1]) + idx)
    except:
        parts.append(str(idx))
    new_ver = '.'.join(parts)
    m = re.match(r'([^\d]*)(\d+)', rel)
    if m:
        prefix, num = m.groups()
        new_rel = f"{prefix}{int(num)+idx}"
    else:
        new_rel = rel
    return f"{new_ver}-{new_rel}"

def get_packager_nick(pkg_name):
    """Fallback: run `rpm -qi pkg_name` to extract Packager nick."""
    try:
        res = subprocess.run(
            ['rpm', '-qi', pkg_name],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            check=True
        )
    except subprocess.CalledProcessError:
        return None

    for line in res.stdout.splitlines():
        if line.startswith('Packager'):
            m = re.search(r'<([^@>]+)@', line)
            return m.group(1) if m else None
    return None

def process_db(engine, num_packages, num_reports, min_days, max_days, extend=False):
    Session = sessionmaker(bind=engine)
    Base.metadata.create_all(engine)
    db = Session()
    logger.info(">>> Processing DB %s", engine.url)

    # 1) Load existing maintainers
    logger.info("Found maintainers: %d", db.query(Maintainer).count())

    # 2) Query `rpm -qa`
    rpm_list = subprocess.check_output(['rpm','-qa'], text=True).splitlines()
    existing_names = {p.name for p in db.query(Package).all()}
    candidates = [r for r in rpm_list
                  if (nm := parse_rpm_name(r)[0]) not in existing_names]
    chosen = (candidates if num_packages == 0
              else random.sample(candidates, min(len(candidates), num_packages)))
    logger.info("Candidates: %d, chosen: %d", len(candidates), len(chosen))

    # 3) Insert packages (+ maintainers, ACL, groups, architectures, updates)
    for full in chosen:
        pkg_name, ver_rel, _ = parse_rpm_name(full)
        if db.query(Package).filter_by(name=pkg_name).first():
            logger.warning("Package `%s` already exists, skipping", pkg_name)
            continue

        info = parse_rpm_info(pkg_name)
        pkg = Package(name=pkg_name, description=info.get('summary',''))
        db.add(pkg)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            logger.warning("IntegrityError on inserting `%s`, skip", pkg_name)
            continue

        pid = pkg.package_id
        logger.info("Inserted package `%s` (ID=%d)", pkg_name, pid)

        if not extend:
            # 3.1) Ensure packager maintainer exists & ACL
            pm = None
            nick = info.get('packager_nick')
            if nick:
                pm = db.query(Maintainer).filter_by(nickname=nick).first()
                if not pm:
                    pm = Maintainer(
                        nickname=nick,
                        full_name=info.get('packager_full', nick)
                    )
                    db.add(pm)
                    try:
                        db.commit()
                    except IntegrityError:
                        db.rollback()
                    else:
                        logger.info("Inserted maintainer `%s`", nick)

                if pm:
                    db.add(ACL(
                        package_id=pid,
                        maintainer_id=pm.maintainer_id,
                        role='packager'
                    ))

            # 3.2) RPM group
            grp = info.get('group') or random.choice(RPM_GROUPS)
            db.add(PackageGroup(package_id=pid, group_name=grp))

            # 3.3) Architecture
            arch = info.get('arch')
            if arch:
                db.add(PackageArchitecture(package_id=pid, architecture=arch))

            # 3.4) Initial updates
            num_upd = random.randint(2, 3)
            dates = random_dates(num_upd, min_days, max_days)
            for idx, dt in enumerate(dates):
                base_ver = f"{info.get('version','')}-{info.get('release','')}"
                uv = base_ver if idx == 0 else bump_version_release(base_ver, idx)
                changelog = f"update {pkg_name} to {uv}"

                if pm:
                    updater_id = pm.maintainer_id
                else:
                    fallback_nick = get_packager_nick(pkg_name)
                    maint = (db.query(Maintainer)
                              .filter_by(nickname=fallback_nick)
                              .first()) if fallback_nick else None
                    if not maint:
                        logger.warning("Skipping update for %s: no maintainer", pkg_name)
                        continue
                    updater_id = maint.maintainer_id

                db.add(PackageUpdate(
                    package_id     = pid,
                    updater_id     = updater_id,
                    update_version = uv,
                    update_date    = dt,
                    changelog      = changelog
                ))

            db.commit()

    # 4) Insert bug reports
    all_pkgs = db.query(Package).all()

    # Map package_id -> ACL maintainer_ids
    owners_map = defaultdict(list)
    for entry in db.query(ACL).all():
        owners_map[entry.package_id].append(entry.maintainer_id)

    # Cache packager nick
    packager_map = {}
    for pkg in all_pkgs:
        nick = get_packager_nick(pkg.name)
        if nick:
            packager_map[pkg.package_id] = nick
        else:
            logger.warning("No packager info for package %s", pkg.name)

    inserted = 0
    for _ in range(num_reports):
        pkg = random.choice(all_pkgs)

        if owners_map[pkg.package_id]:
            assignee_id = random.choice(owners_map[pkg.package_id])
        else:
            nick = packager_map.get(pkg.package_id)
            if not nick:
                logger.warning("Skipping report for %s: no packager", pkg.name)
                continue
            maint = db.query(Maintainer).filter_by(nickname=nick).first()
            if not maint:
                logger.warning("Skipping report for %s: maintainer '%s' missing", pkg.name, nick)
                continue
            assignee_id = maint.maintainer_id

        rpt = Report(
            package_id   = pkg.package_id,
            status       = 'NEW',
            resolution   = '',
            assignee_id  = assignee_id,
            reporter     = f"user{random.randint(1000,9999)}@example.com",
            summary      = random.choice(SUMMARY_OPTIONS),
            last_changed = random_dates(1, min_days, max_days)[0]
        )
        db.add(rpt)
        inserted += 1

    db.commit()
    logger.info("Inserted %d bug reports (requested %d)", inserted, num_reports)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description="Populate ALT-Sisyphus DB from `rpm -qa`/`rpm -qi`"
    )
    parser.add_argument('--packages', type=int, default=100,
                        help="How many packages to insert (0 = all candidates)")
    parser.add_argument('--reports', type=int, default=20,
                        help="How many bug-reports to generate")
    parser.add_argument('--min-days', type=int, default=0,
                        help="Minimum days ago for timestamps")
    parser.add_argument('--max-days', type=int, default=180,
                        help="Maximum days ago for timestamps")
    parser.add_argument('--extend', action='store_true',
                        help="Only insert packages & reports; skip ACL/arch/groups/updates")
    args = parser.parse_args()

    engines = [
        create_engine('sqlite:///sisyphus_pg.db', echo=False),
        create_engine('sqlite:///sisyphus_ch.db', echo=False)
    ]

    for eng in engines:
        process_db(
            eng,
            num_packages=args.packages,
            num_reports=args.reports,
            min_days=args.min_days,
            max_days=args.max_days,
            extend=args.extend
        )


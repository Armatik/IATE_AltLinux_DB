# app.py

from flask import Flask, render_template, request, redirect, url_for, session, flash
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from models import (
    Base,
    Package, Maintainer, ACL,
    PackageArchitecture, PackageUpdate,
    PackageGroup, Report
)
from datetime import datetime, date

app = Flask(__name__)
app.secret_key = 'secretkey'

# Два SQLite-файла, переключается через session['db_type']
engine_pg = create_engine('sqlite:///sisyphus_pg.db', echo=False)
engine_ch = create_engine('sqlite:///sisyphus_ch.db', echo=False)
SessionPG = sessionmaker(bind=engine_pg)
SessionCH = sessionmaker(bind=engine_ch)
Base.metadata.create_all(engine_pg)
Base.metadata.create_all(engine_ch)

def get_db():
    return SessionCH() if session.get('db_type') == 'clickhouse' else SessionPG()

# Константы для баг-репортов
STATUSES    = ['NEW','UNCONFIRMED','CONFIRMED','IN_PROGRESS','RESOLVED','VERIFIED','CLOSED']
ARCHITECTURE_OPTIONS = ['i586','x86_64','aarch64','armh','noarch']
RESOLUTIONS = ['', 'FIXED','INVALID','WONTFIX','DUPLICATE','WORKSFORME','MOVED','NOTABUG','NOTOURBUG','INSUFFICIENTDATA']
# Список групп (как в вашей спецификации)
PREDEFINED_GROUPS = [
    "Accessibility","Archiving/Backup","Archiving/Cd burning","Archiving/Compression",
    "Archiving/Other","Books/Computer books","Books/Faqs","Books/Howtos","Books/Literature",
    "Books/Other","Communications","Databases","Development/C","Development/C++",
    "Development/Databases","Development/Debug","Development/Debuggers","Development/Documentation",
    "Development/Erlang","Development/Functional","Development/GNOME and GTK+","Development/Haskell",
    "Development/Java","Development/KDE and QT","Development/Kernel","Development/Lisp",
    "Development/ML","Development/Objective-C","Development/Other","Development/Perl",
    "Development/Python","Development/Python3","Development/Ruby","Development/Scheme",
    "Development/Tcl","Development/Tools","Documentation","Editors","Education","Emulators",
    "Engineering","File tools","Games/Adventure","Games/Arcade","Games/Boards","Games/Cards",
    "Games/Educational","Games/Other","Games/Puzzles","Games/Sports","Games/Strategy",
    "Graphical desktop/Enlightenment","Graphical desktop/FVWM based","Graphical desktop/GNOME",
    "Graphical desktop/GNUstep","Graphical desktop/Icewm","Graphical desktop/KDE",
    "Graphical desktop/MATE","Graphical desktop/Motif","Graphical desktop/Other",
    "Graphical desktop/Rox","Graphical desktop/Sawfish","Graphical desktop/Sugar",
    "Graphical desktop/Window Maker","Graphical desktop/XFce","Graphics","Monitoring",
    "Networking/Chat","Networking/DNS","Networking/File transfer","Networking/FTN",
    "Networking/IRC","Networking/Instant messaging","Networking/Mail","Networking/News",
    "Networking/Other","Networking/Remote access","Networking/WWW","Office","Other",
    "Publishing","Sciences/Astronomy","Sciences/Biology","Sciences/Chemistry",
    "Sciences/Computer science","Sciences/Geosciences","Sciences/Mathematics",
    "Sciences/Medicine","Sciences/Other","Sciences/Physics","Security/Antivirus",
    "Security/Networking","Shells","Sound","System/Base","System/Configuration/Boot and Init",
    "System/Configuration/Hardware","System/Configuration/Networking","System/Configuration/Other",
    "System/Configuration/Packaging","System/Configuration/Printing","System/Fonts/Console",
    "System/Fonts/True type","System/Fonts/Type1","System/Fonts/X11 bitmap",
    "System/Internationalization","System/Kernel and hardware","System/Libraries",
    "System/Legacy libraries","System/Servers","System/Servers/ZProducts","System/X11",
    "System/XFree86","Terminals","Text tools","Toys","Video"
]


# Границы допустимых дат для всех форм
DATE_MIN = date(2001, 1, 1)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/switch_db/<db>')
def switch_db(db):
    session['db_type'] = db
    return redirect(url_for('index'))


# --- MAINTAINERS CRUD w/ filter & sort ---
@app.route('/maintainers')
def list_maintainers():
    db = get_db()
    f_id    = request.args.get('maintainer_id','').strip()
    f_nick  = request.args.get('nickname','').strip()
    f_full  = request.args.get('full_name','').strip()
    sort_by  = request.args.get('sort_by','maintainer_id')
    sort_dir = request.args.get('sort_dir','asc')

    q = db.query(Maintainer)
    if f_id:
        try: q = q.filter(Maintainer.maintainer_id == int(f_id))
        except: pass
    if f_nick:
        q = q.filter(Maintainer.nickname.contains(f_nick))
    if f_full:
        q = q.filter(Maintainer.full_name.contains(f_full))

    if sort_by in ['maintainer_id','nickname','full_name']:
        col = getattr(Maintainer, sort_by)
        q = q.order_by(col.desc() if sort_dir=='desc' else col.asc())

    return render_template('maintainers.html',
        maintainers=q.all(),
        filters={'maintainer_id':f_id,'nickname':f_nick,'full_name':f_full},
        sort={'by':sort_by,'dir':sort_dir}
    )

@app.route('/maintainers/add', methods=['GET','POST'])
def add_maintainer():
    db = get_db()
    if request.method == 'POST':
        nick = request.form.get('nickname','').strip()
        full = request.form.get('full_name','').strip()
        if not nick or not full:
            flash('Никнейм и полное имя обязательны', 'danger')
            return render_template('add_maintainer.html', form_data=request.form)
        db.add(Maintainer(nickname=nick, full_name=full))
        db.commit()
        flash(f'Мейнтейнер «{nick}» добавлен', 'success')
        return redirect(url_for('list_maintainers'))
    return render_template('add_maintainer.html', form_data={})

@app.route('/maintainers/edit/<int:id>', methods=['GET','POST'])
def edit_maintainer(id):
    db = get_db()
    m = db.query(Maintainer).get(id)
    if not m:
        flash('Мейнтейнер не найден', 'danger')
        return redirect(url_for('list_maintainers'))
    if request.method == 'POST':
        nick = request.form.get('nickname','').strip()
        full = request.form.get('full_name','').strip()
        if not nick or not full:
            flash('Никнейм и полное имя обязательны', 'danger')
        else:
            m.nickname = nick
            m.full_name = full
            db.commit()
            flash('Мейнтейнер обновлён', 'success')
            return redirect(url_for('list_maintainers'))
    return render_template('edit_maintainer.html', maintainer=m)

@app.route('/maintainers/delete/<int:id>')
def delete_maintainer(id):
    db = get_db()
    m = db.query(Maintainer).get(id)
    if m:
        db.delete(m)
        db.commit()
        flash('Мейнтейнер удалён', 'success')
    else:
        flash('Мейнтейнер не найден', 'danger')
    return redirect(url_for('list_maintainers'))


# --- PACKAGES CRUD w/ filter & sort ---
@app.route('/packages')
def list_packages():
    db = get_db()
    f_id   = request.args.get('package_id','').strip()
    f_name = request.args.get('name','').strip()
    f_desc = request.args.get('description','').strip()
    sort_by  = request.args.get('sort_by','package_id')
    sort_dir = request.args.get('sort_dir','asc')

    q = db.query(Package)
    if f_id:
        try: q = q.filter(Package.package_id == int(f_id))
        except: pass
    if f_name:
        q = q.filter(Package.name.contains(f_name))
    if f_desc:
        q = q.filter(Package.description.contains(f_desc))

    if sort_by in ['package_id','name','description']:
        col = getattr(Package, sort_by)
        q = q.order_by(col.desc() if sort_dir=='desc' else col.asc())

    return render_template('packages.html',
        packages=q.all(),
        filters={'package_id':f_id,'name':f_name,'description':f_desc},
        sort={'by':sort_by,'dir':sort_dir}
    )

@app.route('/packages/add', methods=['GET','POST'])
def add_package():
    db = get_db()
    if request.method == 'POST':
        name        = request.form.get('name','').strip()
        description = request.form.get('description','').strip()
        if not name or not description:
            flash('Поля «Имя» и «Описание» обязательны', 'danger')
            return render_template('add_package.html', form_data=request.form)
        db.add(Package(name=name, description=description))
        db.commit()
        flash(f'Пакет «{name}» добавлен', 'success')
        return redirect(url_for('list_packages'))
    return render_template('add_package.html', form_data={})

@app.route('/packages/complex_add', methods=['GET','POST'])
def complex_add_package():
    db = get_db()
    if request.method == 'POST':
        f = request.form
        name        = f.get('name','').strip()
        description = f.get('description','').strip()
        man_id      = f.get('maintainer_id')
        grp         = f.get('group_name','')
        archs       = f.getlist('architectures')
        version     = f.get('version','').strip()
        date_s      = f.get('update_date','').strip()
        changelog   = f.get('changelog','').strip()

        errors = []
        if not name:        errors.append('Имя пакета обязательно')
        if not description: errors.append('Описание пакета обязательно')
        if not man_id:      errors.append('Сопровождающий обязателен')
        if not grp:         errors.append('Группа обязательна')
        if not archs:       errors.append('Хотя бы одна архитектура обязательна')
        if not version:     errors.append('Версия обязательна')
        if not date_s:      errors.append('Дата обновления обязательна')
        if not changelog:   errors.append('Описание обновления обязательно')

        if errors:
            for msg in errors:
                flash(msg, 'danger')
            return render_template(
                'add_complex_package.html',
                maintainers=db.query(Maintainer).all(),
                predefined_groups=PREDEFINED_GROUPS,
                form_data=f
            )

        # 1) создаём пакет
        pkg = Package(name=name, description=description)
        db.add(pkg); db.commit()
        pid = pkg.package_id

        # 2) ACL
        db.add(ACL(package_id=pid, maintainer_id=int(man_id), role='owner'))

        # 3) Группа
        db.add(PackageGroup(package_id=pid, group_name=grp))

        # 4) Архитектуры
        for a in archs:
            db.add(PackageArchitecture(package_id=pid, architecture=a))

        # 5) Первое обновление
        upd_date = datetime.fromisoformat(date_s)
        db.add(PackageUpdate(
            package_id=pid,
            updater_id=int(man_id),
            update_version=version,
            update_date=upd_date,
            changelog=changelog
        ))

        db.commit()
        flash('Пакет и все связи успешно созданы', 'success')
        return redirect(url_for('list_packages'))

    # GET-запрос — передаём пустой MultiDict, поддерживающий getlist
    return render_template(
        'add_complex_package.html',
        maintainers=db.query(Maintainer).all(),
        predefined_groups=PREDEFINED_GROUPS,
        form_data=request.form
    )


@app.route('/packages/edit/<int:id>', methods=['GET','POST'])
def edit_package(id):
    db = get_db()
    pkg = db.query(Package).get(id)
    if not pkg:
        flash('Пакет не найден', 'danger')
        return redirect(url_for('list_packages'))
    if request.method == 'POST':
        name        = request.form.get('name','').strip()
        description = request.form.get('description','').strip()
        if not name or not description:
            flash('Имя и описание обязательны', 'danger')
        else:
            pkg.name = name
            pkg.description = description
            db.commit()
            flash('Пакет обновлён', 'success')
            return redirect(url_for('list_packages'))
    return render_template('edit_package.html', pkg=pkg)

@app.route('/packages/delete/<int:id>')
def delete_package(id):
    db = get_db()
    pkg = db.query(Package).get(id)
    if pkg:
        db.delete(pkg)
        db.commit()
        flash('Пакет удалён', 'success')
    else:
        flash('Пакет не найден', 'danger')
    return redirect(url_for('list_packages'))

@app.route('/packages/<int:id>')
def package_detail(id):
    db = get_db()
    pkg = db.query(Package).get(id)
    if not pkg:
        flash('Пакет не найден', 'danger')
        return redirect(url_for('list_packages'))

    acl_entries   = db.query(ACL).filter_by(package_id=id).all()
    architectures = db.query(PackageArchitecture).filter_by(package_id=id).all()
    groups        = db.query(PackageGroup).filter_by(package_id=id).all()
    updates       = db.query(PackageUpdate)\
                        .filter_by(package_id=id)\
                        .order_by(PackageUpdate.update_date.desc())\
                        .all()
    bugs          = db.query(Report).filter_by(package_id=id).all()

    return render_template('package_detail.html',
                           pkg=pkg,
                           acl_entries=acl_entries,
                           architectures=architectures,
                           groups=groups,
                           updates=updates,
                           bugs=bugs)


# --- ARCHITECTURES CRUD w/ filter & sort ---
@app.route('/architectures')
def list_architectures():
    db = get_db()
    f_id    = request.args.get('arch_id','').strip()
    f_pkg   = request.args.get('package_id','').strip()
    f_arch  = request.args.get('architecture','').strip()
    sort_by  = request.args.get('sort_by','arch_id')
    sort_dir = request.args.get('sort_dir','asc')

    q = db.query(PackageArchitecture)
    if f_id:
        try: q = q.filter(PackageArchitecture.arch_id == int(f_id))
        except: pass
    if f_pkg:
        try: q = q.filter(PackageArchitecture.package_id == int(f_pkg))
        except: pass
    if f_arch:
        q = q.filter(PackageArchitecture.architecture.contains(f_arch))

    if sort_by in ['arch_id','package_id','architecture']:
        col = getattr(PackageArchitecture, sort_by)
        q = q.order_by(col.desc() if sort_dir=='desc' else col.asc())

    return render_template('architectures.html',
        archs=q.all(),
        packages=db.query(Package).all(),
        filters={'arch_id':f_id,'package_id':f_pkg,'architecture':f_arch},
        sort={'by':sort_by,'dir':sort_dir}
    )

@app.route('/architectures/add', methods=['GET','POST'])
def add_architecture():
    db = get_db()
    # для проверки и повторного вывода введённых данных
    form = request.form
    if request.method == 'POST':
        pkg_id = form.get('package_id')
        arch   = form.get('architecture','').strip()
        errors = []
        if not pkg_id:
            errors.append('Поле «Пакет» обязательно')
        if arch not in ARCHITECTURE_OPTIONS:
            errors.append('Выберите одну из предложенных архитектур')
        if errors:
            for msg in errors:
                flash(msg, 'danger')
            # при ошибках рендерим с сохранёнными данными
            return render_template(
                'add_architecture.html',
                packages=db.query(Package).all(),
                arch_options=ARCHITECTURE_OPTIONS,
                form_data=form
            )
        # сохраняем
        db.add(PackageArchitecture(package_id=int(pkg_id), architecture=arch))
        db.commit()
        flash(f'Архитектура «{arch}» добавлена для пакета', 'success')
        return redirect(url_for('list_architectures'))

    # GET — передаём пустой MultiDict, поддерживает get()
    return render_template(
        'add_architecture.html',
        packages=db.query(Package).all(),
        arch_options=ARCHITECTURE_OPTIONS,
        form_data=form
    )

@app.route('/architectures/delete/<int:id>')
def delete_architecture(id):
    db = get_db()
    a = db.query(PackageArchitecture).get(id)
    if a:
        db.delete(a)
        db.commit()
        flash('Архитектура удалена', 'success')
    else:
        flash('Архитектура не найдена', 'danger')
    return redirect(url_for('list_architectures'))


# --- GROUPS CRUD w/ filter & sort ---
@app.route('/groups')
def list_groups():
    db = get_db()
    f_id    = request.args.get('group_id','').strip()
    f_pkg   = request.args.get('package_id','').strip()
    f_name  = request.args.get('group_name','').strip()
    sort_by  = request.args.get('sort_by','group_id')
    sort_dir = request.args.get('sort_dir','asc')

    q = db.query(PackageGroup)
    if f_id:
        try: q = q.filter(PackageGroup.group_id == int(f_id))
        except: pass
    if f_pkg:
        try: q = q.filter(PackageGroup.package_id == int(f_pkg))
        except: pass
    if f_name:
        q = q.filter(PackageGroup.group_name.contains(f_name))

    if sort_by in ['group_id','package_id','group_name']:
        col = getattr(PackageGroup, sort_by)
        q = q.order_by(col.desc() if sort_dir=='desc' else col.asc())

    return render_template('groups.html',
        groups=q.all(),
        packages=db.query(Package).all(),
        filters={'group_id':f_id,'package_id':f_pkg,'group_name':f_name},
        sort={'by':sort_by,'dir':sort_dir}
    )

@app.route('/groups/add', methods=['GET','POST'])
def add_group():
    db = get_db()
    if request.method == 'POST':
        pkg_id = request.form.get('package_id')
        name   = request.form.get('group_name','').strip()
        if not pkg_id or not name:
            flash('Поля «Пакет» и «Название группы» обязательны', 'danger')
        else:
            db.add(PackageGroup(package_id=int(pkg_id), group_name=name))
            db.commit()
            flash('Группа пакета добавлена', 'success')
            return redirect(url_for('list_groups'))
    return render_template('add_group.html', packages=db.query(Package).all())

@app.route('/groups/delete/<int:id>')
def delete_group(id):
    db = get_db()
    g = db.query(PackageGroup).get(id)
    if g:
        db.delete(g)
        db.commit()
        flash('Группа удалена', 'success')
    else:
        flash('Группа не найдена', 'danger')
    return redirect(url_for('list_groups'))


# --- UPDATES CRUD w/ filter & sort & date constraint ---
@app.route('/updates')
def list_updates():
    db = get_db()
    f_id      = request.args.get('update_id','').strip()
    f_pkg     = request.args.get('package_id','').strip()
    f_man     = request.args.get('updater_id','').strip()
    f_ver     = request.args.get('update_version','').strip()
    f_date    = request.args.get('update_date','').strip()
    sort_by   = request.args.get('sort_by','update_id')
    sort_dir  = request.args.get('sort_dir','asc')

    q = db.query(PackageUpdate)
    if f_id:
        try: q = q.filter(PackageUpdate.update_id == int(f_id))
        except: pass
    if f_pkg:
        try: q = q.filter(PackageUpdate.package_id == int(f_pkg))
        except: pass
    if f_man:
        try: q = q.filter(PackageUpdate.updater_id == int(f_man))
        except: pass
    if f_ver:
        q = q.filter(PackageUpdate.update_version.contains(f_ver))
    if f_date:
        try:
            d = datetime.fromisoformat(f_date)
            q = q.filter(PackageUpdate.update_date == d)
        except: pass

    if sort_by in ['update_id','package_id','updater_id','update_version','update_date']:
        col = getattr(PackageUpdate, sort_by)
        q = q.order_by(col.desc() if sort_dir=='desc' else col.asc())

    return render_template('updates.html',
        updates=q.all(),
        packages=db.query(Package).all(),
        maintainers=db.query(Maintainer).all(),
        filters={
            'update_id':f_id,'package_id':f_pkg,'updater_id':f_man,
            'update_version':f_ver,'update_date':f_date
        },
        sort={'by':sort_by,'dir':sort_dir}
    )

@app.route('/updates/add', methods=['GET','POST'])
def add_update():
    db = get_db()
    today_iso = date.today().isoformat()
    if request.method == 'POST':
        pkg_id = request.form.get('package_id')
        man_id = request.form.get('updater_id')
        ver    = request.form.get('update_version','').strip()
        date_s = request.form.get('update_date','').strip()
        log    = request.form.get('changelog','').strip()

        errors = []
        if not pkg_id: errors.append('Выберите пакет')
        if not man_id: errors.append('Выберите мейнтейнера')
        if not ver:    errors.append('Укажите версию')
        if not date_s: errors.append('Укажите дату')
        if not log:    errors.append('Укажите описание')

        try:
            upd_dt = datetime.fromisoformat(date_s).date()
            if upd_dt < DATE_MIN or upd_dt > date.today():
                errors.append(f'Дата должна быть между {DATE_MIN} и {today_iso}')
        except:
            errors.append('Неверный формат даты')

        if errors:
            for msg in errors:
                flash(msg, 'danger')
            return render_template('add_update.html',
                                   packages=db.query(Package).all(),
                                   maintainers=db.query(Maintainer).all(),
                                   date_min=DATE_MIN.isoformat(),
                                   date_max=today_iso,
                                   form_data=request.form)

        upd = PackageUpdate(
            package_id=int(pkg_id),
            updater_id=int(man_id),
            update_version=ver,
            update_date=datetime.fromisoformat(date_s),
            changelog=log
        )
        db.add(upd)
        db.commit()
        flash('Обновление добавлено', 'success')
        return redirect(url_for('list_updates'))

    return render_template('add_update.html',
                           packages=db.query(Package).all(),
                           maintainers=db.query(Maintainer).all(),
                           date_min=DATE_MIN.isoformat(),
                           date_max=date.today().isoformat(),
                           form_data={})

@app.route('/updates/delete/<int:id>')
def delete_update(id):
    db = get_db()
    u = db.query(PackageUpdate).get(id)
    if u:
        db.delete(u)
        db.commit()
        flash('Обновление удалено', 'success')
    else:
        flash('Обновление не найдено', 'danger')
    return redirect(url_for('list_updates'))


# --- REPORTS CRUD w/ filter & sort & date constraint ---
@app.route('/reports')
def list_reports():
    db = get_db()
    f_id    = request.args.get('report_id','').strip()
    f_pkg   = request.args.get('package_id','').strip()
    f_stat  = request.args.get('status','').strip()
    f_res   = request.args.get('resolution','').strip()
    f_assn  = request.args.get('assignee_id','').strip()
    f_rep   = request.args.get('reporter','').strip()
    sort_by = request.args.get('sort_by','id')
    sort_dir= request.args.get('sort_dir','asc')

    q = db.query(Report)
    if f_id:
        try: q = q.filter(Report.id == int(f_id))
        except: pass
    if f_pkg:
        try: q = q.filter(Report.package_id == int(f_pkg))
        except: pass
    if f_stat:
        q = q.filter(Report.status.contains(f_stat))
    if f_res:
        q = q.filter(Report.resolution.contains(f_res))
    if f_assn:
        try: q = q.filter(Report.assignee_id == int(f_assn))
        except: pass
    if f_rep:
        q = q.filter(Report.reporter.contains(f_rep))

    if sort_by in ['id','package_id','status','resolution','assignee_id','reporter','last_changed']:
        col = getattr(Report, sort_by)
        q = q.order_by(col.desc() if sort_dir=='desc' else col.asc())

    return render_template('reports.html',
        reports=q.all(),
        packages=db.query(Package).all(),
        maintainers=db.query(Maintainer).all(),
        statuses=STATUSES,
        resolutions=RESOLUTIONS,
        filters={
            'report_id':f_id,'package_id':f_pkg,'status':f_stat,
            'resolution':f_res,'assignee_id':f_assn,'reporter':f_rep
        },
        sort={'by':sort_by,'dir':sort_dir}
    )

@app.route('/reports/add', methods=['GET','POST'])
def add_report():
    db = get_db()
    today_iso = date.today().isoformat()
    if request.method == 'POST':
        pkg_id      = request.form.get('package_id')
        status      = request.form.get('status','')
        resolution  = request.form.get('resolution','')
        assignee_id = request.form.get('assignee_id')
        reporter    = request.form.get('reporter','').strip()
        summary     = request.form.get('summary','').strip()
        last_changed= request.form.get('last_changed','').strip()

        errors = []
        if not pkg_id:   errors.append("Выберите пакет")
        if status not in STATUSES: errors.append("Выберите корректный статус")
        if resolution and resolution not in RESOLUTIONS: errors.append("Выберите корректный вердикт")
        if not assignee_id: errors.append("Выберите исполнителя")
        if not reporter:  errors.append("Заполните поле «Автор отчёта»")
        if not summary:   errors.append("Заполните поле «Краткое описание»")

        if last_changed:
            try:
                lc = datetime.fromisoformat(last_changed).date()
                if lc < DATE_MIN or lc > date.today():
                    errors.append(f"Дата отчёта должна быть между {DATE_MIN} и {today_iso}")
            except:
                errors.append("Неверный формат даты")

        if errors:
            for msg in errors:
                flash(msg, 'danger')
            return render_template('add_report.html',
                packages=db.query(Package).all(),
                maintainers=db.query(Maintainer).all(),
                statuses=STATUSES,
                resolutions=RESOLUTIONS,
                date_min=DATE_MIN.isoformat(),
                date_max=today_iso,
                form_data=request.form
            )

        rpt = Report(
            package_id=int(pkg_id),
            status=status,
            resolution=resolution,
            assignee_id=int(assignee_id),
            reporter=reporter,
            summary=summary,
            last_changed=datetime.fromisoformat(last_changed) if last_changed else None
        )
        db.add(rpt)
        db.commit()
        flash('Баг-репорт добавлен', 'success')
        return redirect(url_for('list_reports'))

    return render_template('add_report.html',
        packages=db.query(Package).all(),
        maintainers=db.query(Maintainer).all(),
        statuses=STATUSES,
        resolutions=RESOLUTIONS,
        date_min=DATE_MIN.isoformat(),
        date_max=date.today().isoformat(),
        form_data={}
    )

@app.route('/reports/edit/<int:id>', methods=['GET','POST'])
def edit_report(id):
    db = get_db()
    rpt = db.query(Report).get(id)
    if not rpt:
        flash('Отчёт не найден', 'danger')
        return redirect(url_for('list_reports'))

    today_iso = date.today().isoformat()
    if request.method == 'POST':
        pkg_id      = request.form.get('package_id')
        status      = request.form.get('status','')
        resolution  = request.form.get('resolution','')
        assignee_id = request.form.get('assignee_id')
        reporter    = request.form.get('reporter','').strip()
        summary     = request.form.get('summary','').strip()
        last_changed= request.form.get('last_changed','').strip()

        errors = []
        if not pkg_id:   errors.append("Выберите пакет")
        if status not in STATUSES: errors.append("Выберите корректный статус")
        if resolution and resolution not in RESOLUTIONS: errors.append("Выберите корректный вердикт")
        if not assignee_id: errors.append("Выберите исполнителя")
        if not reporter:  errors.append("Заполните поле «Автор отчёта»")
        if not summary:   errors.append("Заполните поле «Краткое описание»")

        if last_changed:
            try:
                lc = datetime.fromisoformat(last_changed).date()
                if lc < DATE_MIN or lc > date.today():
                    errors.append(f"Дата отчёта должна быть между {DATE_MIN} и {today_iso}")
            except:
                errors.append("Неверный формат даты")

        if errors:
            for msg in errors:
                flash(msg, 'danger')
            return render_template('edit_report.html',
                report=rpt,
                packages=db.query(Package).all(),
                maintainers=db.query(Maintainer).all(),
                statuses=STATUSES,
                resolutions=RESOLUTIONS,
                date_min=DATE_MIN.isoformat(),
                date_max=today_iso
            )

        rpt.package_id   = int(pkg_id)
        rpt.status       = status
        rpt.resolution   = resolution
        rpt.assignee_id  = int(assignee_id)
        rpt.reporter     = reporter
        rpt.summary      = summary
        rpt.last_changed = datetime.fromisoformat(last_changed) if last_changed else None
        db.commit()
        flash('Баг-репорт обновлён', 'success')
        return redirect(url_for('list_reports'))

    return render_template('edit_report.html',
        report=rpt,
        packages=db.query(Package).all(),
        maintainers=db.query(Maintainer).all(),
        statuses=STATUSES,
        resolutions=RESOLUTIONS,
        date_min=DATE_MIN.isoformat(),
        date_max=date.today().isoformat()
    )

@app.route('/reports/delete/<int:id>')
def delete_report(id):
    db = get_db()
    r = db.query(Report).get(id)
    if r:
        db.delete(r)
        db.commit()
        flash('Баг-репорт удалён', 'success')
    else:
        flash('Отчёт не найден', 'danger')
    return redirect(url_for('list_reports'))


# --- ACL CRUD w/ filter & sort ---
@app.route('/acl')
def list_acl():
    db = get_db()
    f_id    = request.args.get('acl_id','').strip()
    f_pkg   = request.args.get('package_id','').strip()
    f_man   = request.args.get('maintainer_id','').strip()
    f_role  = request.args.get('role','').strip()
    sort_by = request.args.get('sort_by','acl_id')
    sort_dir= request.args.get('sort_dir','asc')

    q = db.query(ACL)
    if f_id:
        try: q = q.filter(ACL.acl_id == int(f_id))
        except: pass
    if f_pkg:
        try: q = q.filter(ACL.package_id == int(f_pkg))
        except: pass
    if f_man:
        try: q = q.filter(ACL.maintainer_id == int(f_man))
        except: pass
    if f_role:
        q = q.filter(ACL.role.contains(f_role))

    if sort_by in ['acl_id','package_id','maintainer_id','role']:
        col = getattr(ACL, sort_by)
        q = q.order_by(col.desc() if sort_dir=='desc' else col.asc())

    return render_template('acl.html',
        acl=q.all(),
        packages=db.query(Package).all(),
        maintainers=db.query(Maintainer).all(),
        filters={'acl_id':f_id,'package_id':f_pkg,'maintainer_id':f_man,'role':f_role},
        sort={'by':sort_by,'dir':sort_dir}
    )

@app.route('/acl/add', methods=['GET','POST'])
def add_acl():
    db = get_db()
    if request.method == 'POST':
        pkg_id = request.form.get('package_id')
        man_id = request.form.get('maintainer_id')
        role   = request.form.get('role','').strip()
        if not pkg_id or not man_id or not role:
            flash('Все поля ACL обязательны', 'danger')
        else:
            db.add(ACL(package_id=int(pkg_id), maintainer_id=int(man_id), role=role))
            db.commit()
            flash('ACL-запись добавлена', 'success')
            return redirect(url_for('list_acl'))
    return render_template('add_acl.html',
                           packages=db.query(Package).all(),
                           maintainers=db.query(Maintainer).all())

@app.route('/acl/edit/<int:id>', methods=['GET','POST'])
def edit_acl(id):
    db = get_db()
    entry = db.query(ACL).get(id)
    if not entry:
        flash('ACL-запись не найдена', 'danger')
        return redirect(url_for('list_acl'))
    if request.method == 'POST':
        pkg_id = request.form.get('package_id')
        man_id = request.form.get('maintainer_id')
        role   = request.form.get('role','').strip()
        if not pkg_id or not man_id or not role:
            flash('Все поля ACL обязательны', 'danger')
        else:
            entry.package_id    = int(pkg_id)
            entry.maintainer_id = int(man_id)
            entry.role          = role
            db.commit()
            flash('ACL-запись обновлена', 'success')
            return redirect(url_for('list_acl'))
    return render_template('edit_acl.html',
                           entry=entry,
                           packages=db.query(Package).all(),
                           maintainers=db.query(Maintainer).all())

@app.route('/acl/delete/<int:id>')
def delete_acl(id):
    db = get_db()
    entry = db.query(ACL).get(id)
    if entry:
        db.delete(entry)
        db.commit()
        flash('ACL-запись удалена', 'success')
    else:
        flash('ACL-запись не найдена', 'danger')
    return redirect(url_for('list_acl'))


if __name__ == '__main__':
    app.run(debug=True)


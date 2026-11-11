<div align="center">

# 🤝 MITR

### *Multi-Tenant Task Escalation & Subscription Lifecycle Management Platform*

**Built for Nescube Technology Private Limited**

[![Python](https://img.shields.io/badge/Python-3.11-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
[![Django](https://img.shields.io/badge/Django-5.x-092E20?style=for-the-badge&logo=django&logoColor=white)](https://djangoproject.com)
[![Docker](https://img.shields.io/badge/Docker-Ready-2496ED?style=for-the-badge&logo=docker&logoColor=white)](https://docker.com)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-Supabase-316192?style=for-the-badge&logo=postgresql&logoColor=white)](https://supabase.com)
[![Railway](https://img.shields.io/badge/Deploy-Railway-0B0D0E?style=for-the-badge&logo=railway&logoColor=white)](https://railway.app)

</div>

---

## 📖 What is MITR?

**MITR** (Hindi: *मित्र*, meaning *"Friend / Companion"*) is an enterprise internal workflow automation platform. It was built to solve a real operational problem at Nescube Technology Pvt. Ltd.: tasks assigned verbally or over chat were being forgotten with zero follow-up, client subscriptions were expiring silently, and there was no auditable trail for overdue deliverables.

MITR replaces passive task boards like Jira and Trello with an **aggressive, automated escalation engine** — it actively emails assignees on set time cadences until a task is marked done, enforces mandatory delay justifications, and tracks recurring client subscriptions end-to-end.

---

## 🎯 Core Problems Solved

| Problem | MITR Solution |
|---------|--------------|
| Tasks delegated verbally or over chat are forgotten | Automated email ping-loop on configurable cadences (1 hour → 1 month) until task is completed |
| No accountability for overdue work | Physical "overdue gate" — the system blocks task completion and demands a written `overdue_reason` before proceeding |
| Client subscriptions (OTT / SaaS) lapse silently | Automated countdown warnings at 1 Day, 1 Week, 1 Month before expiry, plus midnight-transition expiration alerts |
| Management has no visibility without meetings | One-click Excel report downloads (`.xlsx`) scoped to Daily / Weekly / Monthly with employee-wise analytics |
| Multiple companies share the same instance | Multi-tenant isolation — every view, task, and subscription is scoped to the logged-in user's `company` |

---

## 🏗️ System Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                          CLIENT BROWSER                             │
│                   (HTTPS  •  Tailwind UI  •  Vanilla JS)            │
└───────────────────────────────┬─────────────────────────────────────┘
                                │  HTTP / HTTPS
                                ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    GUNICORN  WSGI  SERVER                           │
│          2 workers  •  Port $PORT  •  WhiteNoise static files       │
└───────────────────────────────┬─────────────────────────────────────┘
                                │  WSGI Interface
                                ▼
┌─────────────────────────────────────────────────────────────────────┐
│                   DJANGO 5.x  APPLICATION CORE                      │
│                                                                     │
│  ┌─────────────────┐  ┌──────────────────┐  ┌────────────────────┐ │
│  │  URL Routing    │  │  View Layer       │  │  Auth Engine       │ │
│  │  config/urls.py │  │  MITR_app/views  │  │  EmailBackend      │ │
│  │  MITR_app/urls  │  │  Role Decorators │  │  CustomUser model  │ │
│  └────────┬────────┘  └────────┬─────────┘  └────────────────────┘ │
│           │                    │                                    │
│  ┌────────▼────────────────────▼──────────────────────────────────┐ │
│  │                     ORM  /  Model Layer                        │ │
│  │    CustomUser  •  Employee  •  Task  •  Subscription           │ │
│  └────────┬────────────────────────────────────────────────────────┘ │
│           │  Reporting Engine                                       │
│  ┌────────▼────────────────────────────────────────────────────────┐ │
│  │   Pandas + XlsxWriter (Excel)  │  Matplotlib (Progress Charts) │ │
│  └─────────────────────────────────────────────────────────────────┘ │
└──────────────┬────────────────────────────────┬─────────────────────┘
               │  SQL Reads/Writes              │  async_task() dispatch
               ▼                               ▼
┌──────────────────────┐          ┌─────────────────────────────────┐
│   DATABASE           │          │   DJANGO-Q2  TASK QUEUE         │
│                      │          │                                 │
│  SQLite (dev)        │          │  ORM-backed broker (no Redis)   │
│  PostgreSQL (prod)   │◄─────────│  python manage.py qcluster      │
│  (Supabase)          │          │  Single worker process          │
└──────────────────────┘          └───────────────┬─────────────────┘
                                                  │  Scheduled Tasks
                                  ┌───────────────▼─────────────────┐
                                  │   BACKGROUND TASK REGISTRY      │
                                  │                                 │
                                  │  ◉ send_reminder_email          │
                                  │  ◉ check_overdue_tasks (12h)    │
                                  │  ◉ check_subscription_reminders │
                                  │  ◉ check_ended_subscriptions    │
                                  │  ◉ send_subscription_confirm    │
                                  │  ◉ send_subscription_ended      │
                                  └───────────────┬─────────────────┘
                                                  │  SMTP TLS :587
                                                  ▼
                                  ┌───────────────────────────────────┐
                                  │      Gmail SMTP Gateway           │
                                  │   mitr.taskreminder@gmail.com     │
                                  └───────────────┬───────────────────┘
                                                  │
                                                  ▼
                                       [ Employee Inboxes ]
                                       [ Client Inboxes   ]
```

### Process Topology (Single Docker Container via Supervisord)

```
Docker Container
├── [web]     Gunicorn WSGI  →  serves HTTP on $PORT
└── [worker]  python manage.py qcluster  →  processes background tasks
```

Both processes are managed by **supervisord** with `autorestart=true` — if either crashes, it is automatically restarted without taking down the container.

---

## 🗄️ Data Model

```
┌─────────────────────────────────┐         1 : 1         ┌──────────────────────────────────┐
│          CustomUser             │◄──────────────────────►│           Employee               │
│─────────────────────────────────│                        │──────────────────────────────────│
│  id            BigAutoField PK  │                        │  id            BigAutoField PK   │
│  email         EmailField UQ    │                        │  user_id       FK → CustomUser   │
│  username      CharField        │                        │  name          CharField(100)    │
│  company       CharField        │                        │  email         EmailField UQ     │
│  is_superuser  BooleanField     │                        │  phone_number  CharField(15)     │
└─────────────────────────────────┘                        │  company       CharField(100)    │
                                                           │  coordinator   BooleanField      │
                                                           └────────────────┬─────────────────┘
                                                                            │ 1 : N
                                                                            ▼
┌──────────────────────────────────────────────────────────────────────────────────────────────┐
│                                          Task                                                │
│──────────────────────────────────────────────────────────────────────────────────────────────│
│  id                      BigAutoField PK                                                     │
│  task_id                 CharField(50) UNIQUE  (auto-generated: ddmmyyyyHHMMSS)              │
│  title                   CharField(100)                                                      │
│  description             TextField                                                           │
│  email                   EmailField              (client contact)                            │
│  employee_id             FK → Employee CASCADE                                               │
│  remind_every            DurationField           (1 Hour → 1 Month)                         │
│  submission_date         DateField               (deadline)                                  │
│  date_added              DateTimeField           (auto, creation timestamp)                  │
│  completed               BooleanField            (admin/coordinator sign-off)                │
│  employee_marked_completed BooleanField          (employee self-report)                      │
│  next_reminder_date      DateTimeField           (computed: now + remind_every)              │
│  completed_date          DateTimeField NULL                                                   │
│  completed_by_id         FK → CustomUser SET_NULL NULL                                      │
│  completed_at            DateTimeField NULL                                                   │
│  rework_by_id            FK → CustomUser SET_NULL NULL                                      │
│  rework_date             DateTimeField NULL                                                   │
│  overdue_reason          CharField(5000)         (mandatory if past deadline)                │
│  last_overdue_reminder   DateTimeField NULL      (deduplication guard)                       │
│  client_company          CharField(100) NULL                                                 │
│  client_phone_number     CharField(15)                                                       │
└──────────────────────────────────────────────────────────────────────────────────────────────┘

┌───────────────────────────────────────────┐
│               Subscription                │
│───────────────────────────────────────────│
│  id                 BigAutoField PK       │
│  subscription_type  CharField(50)         │
│  description        TextField             │
│  ending_reminder    CharField(20)         │
│       ('1 Day' | '1 Week' | '1 Month')   │
│  customer_name      CharField(100)        │
│  customer_email     EmailField            │
│  customer_phone     CharField(15)         │
│  start_date         DateTimeField auto    │
│  end_date           DateTimeField         │
│  reminder_sent      BooleanField          │
│  end_notification_sent BooleanField       │
└───────────────────────────────────────────┘
```

---

## ⚙️ Tech Stack

| Layer | Technology | Notes |
|-------|-----------|-------|
| **Language** | Python 3.11 | |
| **Framework** | Django 5.x | MVT, ORM, custom auth |
| **Auth** | Custom `EmailBackend` | Email + Password login (no username) |
| **Task Queue** | django-q2 | ORM-backed broker — no Redis needed |
| **Scheduler** | django-q2 `Schedule` model | `python manage.py setup_schedules` |
| **WSGI Server** | Gunicorn | 2 workers, `0.0.0.0:$PORT` |
| **Static Files** | WhiteNoise | Serves `staticfiles/` without Nginx |
| **Process Manager** | Supervisord | Manages gunicorn + qcluster in Docker |
| **Database (dev)** | SQLite 3 | `database/db.sqlite3` |
| **Database (prod)** | PostgreSQL | Managed via Supabase, `dj-database-url` |
| **Email** | Gmail SMTP | Port 587 TLS, App Password |
| **Reporting** | Pandas + XlsxWriter | Streaming `.xlsx` Excel downloads |
| **Charts** | Matplotlib (Agg) | Server-side PNG bar charts |
| **Frontend** | Django Templates + Tailwind CDN | Google Sans, FontAwesome 5, Vanilla JS |
| **Containerization** | Docker | Single container, `python:3.11-slim` base |
| **Deployment** | Railway | Single container deploy |

---

## 🗺️ Routes & Access Control

| URL | View | Method | Access | Description |
|-----|------|--------|--------|-------------|
| `/` | `login_register_view` | GET, POST | Public | Dual-tab login & registration portal |
| `/login_register/` | `login_register_view` | GET, POST | Public | Canonical auth route |
| `/logout/` | `logout_view` | GET | Authenticated | Session termination |
| `/dashboard/` | `dashboard_view` | GET, POST | Employee / Coordinator / Admin | Primary workspace — task list, add task |
| `/dashboard/task/<id>/` | `task_view` | GET, POST | Employee / Admin | Task detail, overdue gate, rework |
| `/add_employee/` | `add_employee_view` | GET, POST | **Admin only** | Onboard new staff |
| `/employee_list/` | `employee_list_view` | GET | Coordinator / Admin | Staff roster + coordinator toggles |
| `/confirm-remove-employee/<id>/` | `confirm_remove_employee` | GET, POST | **Admin only** | Safety confirmation before employee deletion |
| `/employee/<id>/progress/` | `employee_progress` | GET | Coordinator / Admin | Matplotlib bar chart analytics |
| `/summary_report/` | `summary_report` | GET | Coordinator / Admin | Audit center — Daily / Weekly / Monthly |
| `/download_summary_report/...` | `download_summary_report` | GET | Coordinator / Admin | Streaming Excel `.xlsx` download |
| `/update-coordinator/<id>/` | `update_coordinator` | POST | **Admin only** | AJAX coordinator privilege toggle |
| `/subscriptions/` | `subscriptions` | GET | Coordinator / Admin | Client subscription tracker |
| `/add_subscription/` | `add_subscription` | POST | Coordinator / Admin | Provision new subscription + send confirmation emails |

### Role Hierarchy

```
Superuser (Admin)
    │  Full access to all views, all companies
    │  Can promote/demote coordinators
    │
    ├── Coordinator
    │       │  Can see all employees & tasks in their company
    │       │  Can assign tasks, view progress, download reports
    │       │  Can manage subscriptions
    │
    └── Employee
            │  Sees only their own assigned tasks
            │  Can mark tasks as completed (overdue gate applies)
```

---

## 📧 Automated Email Flows

### 1. Task Reminder Loop
```
Task Created
    │
    └──► async_task(send_reminder_email, task.id)
              │
              ▼
         Email sent to employee
              │
              ├── Task still incomplete?
              │       │
              │       └──► Schedule next reminder at (now + remind_every)
              │
              └── Task completed? ──► Stop loop
```

### 2. Overdue Task Escalation
```
check_overdue_tasks()  [runs every 12 hours]
    │
    └──► Query: Task where completed=False AND submission_date < today
              │
              └──► For each overdue task:
                        send_reminder_email(task.id)   [urgent escalation]
```

### 3. Subscription Lifecycle
```
Subscription Added
    │
    ├──► send_subscription_confirmation_email  (immediate, to customer)
    │
check_subscription_reminders()  [runs every 1 hour]
    │
    └──► If (end_date - now) <= ending_reminder threshold AND reminder_sent=False
              └──► send_subscription_reminder_email  →  reminder_sent = True

check_ended_subscriptions()  [runs daily at midnight]
    │
    └──► If end_date <= now AND end_notification_sent=False
              └──► send_subscription_ended_email  →  end_notification_sent = True
```

---

## 🚀 Getting Started

### Prerequisites

- Python 3.11+
- Git

### Local Development (without Docker)

```bash
# 1. Clone the repository
git clone https://github.com/Rishankgupta08/MITR.git
cd MITR

# 2. Create and activate virtual environment
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Set up environment variables
cp .env.example .env
# Edit .env — set SECRET_KEY, EMAIL_HOST_PASSWORD, DATABASE_URL

# 5. Apply database migrations
python manage.py migrate

# 6. Register background task schedules
python manage.py setup_schedules

# 7. Create a superuser (admin account)
python manage.py createsuperuser

# 8. Collect static files
python manage.py collectstatic --noinput

# 9. Start the Django development server
python manage.py runserver 9000

# 10. In a separate terminal — start the task queue worker
python manage.py qcluster
```

Open **http://localhost:9000** in your browser.

---

### Docker (Local)

```bash
# Build the image
docker build -t mitr:local .

# Run with environment file
docker run -p 8000:8000 --env-file .env -e PORT=8000 mitr:local
```

The `entrypoint.sh` automatically runs:
1. `collectstatic`
2. `migrate`
3. `setup_schedules`
4. Starts supervisord → gunicorn + qcluster

---

## 🌐 Production Deployment (Railway + Supabase)

### 1. Set up Supabase PostgreSQL

1. Create a new project at [supabase.com](https://supabase.com)
2. Copy the **Connection String** (URI format)
3. Set `DATABASE_URL=postgres://...` in your Railway environment

### 2. Deploy to Railway

1. Connect your GitHub repository to [Railway](https://railway.app)
2. Railway auto-detects the `Procfile`:
   ```
   web: supervisord -n -c supervisord.conf
   ```
3. Set the following environment variables in Railway's dashboard:

```env
SECRET_KEY=<your-long-random-secret>
DEBUG=false
ALLOWED_HOSTS=your-app.up.railway.app
DATABASE_URL=postgres://user:pass@db.supabase.co:5432/mitr
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_USE_TLS=true
EMAIL_HOST_USER=mitr.taskreminder@gmail.com
EMAIL_HOST_PASSWORD=<gmail-app-password>
DEFAULT_FROM_EMAIL=mitr.taskreminder@gmail.com
PORT=8000
```

4. Deploy — Railway builds the Docker image and runs `entrypoint.sh` automatically.

---

## 🔐 Environment Variables Reference

| Variable | Required | Description |
|----------|----------|-------------|
| `SECRET_KEY` | ✅ | Django secret key. Generate with `python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"` |
| `DEBUG` | ✅ | `false` in production, `true` for local dev |
| `ALLOWED_HOSTS` | ✅ | Comma-separated list: `mitr.example.com,localhost` |
| `DATABASE_URL` | ✅ | Full DB URL. Use `sqlite:///./database/db.sqlite3` locally |
| `EMAIL_HOST` | ✅ | `smtp.gmail.com` |
| `EMAIL_PORT` | ✅ | `587` |
| `EMAIL_USE_TLS` | ✅ | `true` |
| `EMAIL_HOST_USER` | ✅ | Gmail address used to send emails |
| `EMAIL_HOST_PASSWORD` | ✅ | Gmail App Password (not your account password) |
| `DEFAULT_FROM_EMAIL` | ✅ | Sender address displayed in email headers |
| `PORT` | Prod only | Port for Gunicorn to bind (Railway sets this automatically) |

> ⚠️ **Never commit your `.env` file.** It is listed in `.gitignore`. Only `.env.example` (with placeholder values) should be committed.

---

## 🛠️ Management Commands

```bash
# Register all Django-Q periodic task schedules in the database
python manage.py setup_schedules

# Start the background task worker (keeps running)
python manage.py qcluster

# Apply all pending database migrations
python manage.py migrate

# Create a superuser admin account
python manage.py createsuperuser

# Collect static files for production
python manage.py collectstatic --noinput
```

---

## 📁 Project Structure

```
mitr/
├── config/                     # Django project configuration
│   ├── __init__.py
│   ├── settings.py             # All settings, reads from .env
│   ├── urls.py                 # Root URL configuration
│   └── wsgi.py
│
├── MITR_app/                   # Core application
│   ├── backends.py             # Custom EmailBackend for auth
│   ├── decorators.py           # @admin_required, @coordinator_or_admin_required
│   ├── forms.py                # TaskForm, RegistrationForm, LoginForm, EmployeeForm
│   ├── models.py               # CustomUser, Employee, Task, Subscription
│   ├── tasks.py                # All Django-Q background task functions
│   ├── views.py                # All 14 view functions
│   ├── urls.py                 # App-level URL patterns
│   ├── admin.py                # Django admin registrations
│   ├── migrations/             # Database migration files
│   ├── management/
│   │   └── commands/
│   │       └── setup_schedules.py  # Registers Q periodic schedules
│   └── templates/              # Server-rendered HTML templates
│       ├── dashboard.html
│       ├── task_view.html
│       ├── employee_list.html
│       ├── employee_progress.html
│       ├── login_register.html
│       └── summary_report.html
│
├── static/                     # Source static assets
│   └── images/
├── staticfiles/                # Collected static (auto-generated)
├── media/                      # Uploaded/generated files
│   └── progress/               # Matplotlib chart PNGs
├── database/                   # SQLite file (dev only)
│
├── Dockerfile                  # Container definition
├── docker-compose.yml          # (optional local multi-service setup)
├── supervisord.conf            # Manages gunicorn + qcluster
├── entrypoint.sh               # Container startup script
├── Procfile                    # Railway/Heroku process definition
├── requirements.txt            # Python dependencies
├── .env.example                # Environment variable template
├── .gitignore
└── manage.py
```

---

## 🔄 Background Task Schedule

Configured via `python manage.py setup_schedules` and stored in Django-Q's `Schedule` table:

| Task | Schedule | Purpose |
|------|----------|---------|
| `check_overdue_tasks` | Every 12 hours | Finds tasks past deadline, triggers escalation emails |
| `check_subscription_reminders` | Every 1 hour | Sends countdown warnings before subscription expiry |
| `check_ended_subscriptions` | Daily at midnight | Sends expiration notifications |

Individual task reminders are scheduled dynamically via `async_task()` when a task is saved.

---

## 📊 Reporting Engine

MITR generates live Excel reports downloadable from the **Summary Report** page:

- **Scope:** Daily / Weekly / Monthly
- **Company isolation:** Only data from the logged-in user's company
- **Format:** `.xlsx` via XlsxWriter with 12 metadata columns:
  - Task ID, Title, Employee, Description, Client, Submission Date, Status, Completion Date, Completed By, Overdue Reason, Date Added, Duration

---

## 🧪 Known Issues & Roadmap

| Issue | Severity | Status |
|-------|----------|--------|
| Subscription model lacks `company` field — tenant isolation gap | Critical | ⏳ Pending |
| Matplotlib charts written to disk on every request | Medium | ⏳ Pending |
| Sidebar HTML duplicated across 4 templates | Medium | ⏳ Pending |
| "You are unemployed" unprofessional message | Low | ⏳ Pending |
| `<button>` nested inside `<a>` (invalid HTML) | Low | ⏳ Pending |
| Icon-only buttons lack `aria-label` accessibility | Low | ⏳ Pending |

---

## 👥 Contributing

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/your-feature`
3. Make changes and commit: `git commit -m "feat: your feature description"`
4. Push: `git push origin feature/your-feature`
5. Open a Pull Request

---

## 📄 License

Internal use — Nescube Technology Private Limited. All rights reserved.

---

<div align="center">

Made with ❤️ for Nescube Technology Pvt. Ltd.

</div>

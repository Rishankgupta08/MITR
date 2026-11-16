import json
from datetime import date, timedelta
from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.utils import timezone
from MITR_app.models import Employee, Task, Subscription

User = get_user_model()

class BaseTestCase(TestCase):
    def setUp(self):
        self.client = Client()

        # Admin
        self.admin = User.objects.create_superuser(
            username='admin_t', email='admin@test.com',
            password='Admin@1234#', company='CompanyA'
        )

        # Coordinator
        self.coord_user = User.objects.create_user(
            username='coord_t', email='coord@test.com',
            password='Coord@1234#', company='CompanyA',
            is_superuser=False
        )
        self.coord_emp = Employee.objects.create(
            user=self.coord_user, name='Test Coordinator',
            email='coord@test.com', company='CompanyA',
            coordinator=True, phone_number='9000000001'
        )

        # Employee CompanyA
        self.emp_user = User.objects.create_user(
            username='emp_t', email='emp@test.com',
            password='Emp@1234#', company='CompanyA',
            is_superuser=False
        )
        self.employee = Employee.objects.create(
            user=self.emp_user, name='Test Employee',
            email='emp@test.com', company='CompanyA',
            coordinator=False, phone_number='9000000002'
        )

        # Employee CompanyB (different tenant)
        self.other_user = User.objects.create_user(
            username='other_t', email='other@test.com',
            password='Other@1234#', company='CompanyB',
            is_superuser=False
        )
        self.other_emp = Employee.objects.create(
            user=self.other_user, name='Other Employee',
            email='other@test.com', company='CompanyB',
            coordinator=False, phone_number='9000000003'
        )

        # Task CompanyA
        self.task_a = Task.objects.create(
            title='Task Alpha CompanyA',
            description='Test task A',
            email='client@a.com',
            employee=self.employee,
            remind_every=timedelta(hours=1),
            submission_date=date.today() + timedelta(days=7),
            client_company='Client A',
            client_phone_number='9000000004'
        )

        # Task CompanyB
        self.task_b = Task.objects.create(
            title='Task Beta CompanyB',
            description='Test task B',
            email='client@b.com',
            employee=self.other_emp,
            remind_every=timedelta(hours=1),
            submission_date=date.today() + timedelta(days=7),
            client_company='Client B',
            client_phone_number='9000000005'
        )

        # Subscription CompanyA
        self.sub_a = Subscription.objects.create(
            subscription_type='netflix',
            description='CompanyA Netflix',
            ending_reminder='1_week',
            customer_name='Customer Alpha',
            customer_email='alpha@a.com',
            customer_phone='9000000006',
            end_date=timezone.now() + timedelta(days=30),
            company='CompanyA'
        )

        # Subscription CompanyB
        self.sub_b = Subscription.objects.create(
            subscription_type='amazon_prime',
            description='CompanyB Prime',
            ending_reminder='1_week',
            customer_name='Customer Beta',
            customer_email='beta@b.com',
            customer_phone='9000000007',
            end_date=timezone.now() + timedelta(days=30),
            company='CompanyB'
        )


# Issue #1 — Report Download Security
class TestIssue1ReportSecurity(BaseTestCase):

    def test_download_requires_login(self):
        """ISSUE #1: Anonymous cannot download report"""
        r = self.client.get(reverse('download_summary_report'))
        self.assertNotEqual(r.status_code, 200,
            'FAIL #1: Anonymous can download report!')

    def test_download_filters_by_company(self):
        """ISSUE #1: Download must not expose other company data"""
        self.client.login(username='coord@test.com',
                          password='Coord@1234#')
        r = self.client.get(reverse('download_summary_report'))
        content = r.content.decode('utf-8', errors='ignore')
        self.assertNotIn('Task Beta CompanyB', content,
            'FAIL #1: CompanyB task in CompanyA download!')

    def test_summary_report_requires_login(self):
        """ISSUE #1: Summary report needs login"""
        r = self.client.get(reverse('summary_report'))
        self.assertNotEqual(r.status_code, 200,
            'FAIL #1: Summary report accessible without login!')


# Issue #2 — update_coordinator CSRF + Auth
class TestIssue2CoordinatorUpdate(BaseTestCase):

    def test_anonymous_cannot_update_coordinator(self):
        """ISSUE #2: Anonymous cannot change coordinator"""
        r = self.client.post(
            reverse('update_coordinator', args=[self.employee.id]),
            data=json.dumps({'coordinator': True}),
            content_type='application/json'
        )
        self.employee.refresh_from_db()
        self.assertFalse(self.employee.coordinator,
            'FAIL #2: Anonymous promoted employee to coordinator!')

    def test_employee_cannot_update_coordinator(self):
        """ISSUE #2: Regular employee cannot promote anyone"""
        self.client.login(username='emp@test.com',
                          password='Emp@1234#')
        self.client.post(
            reverse('update_coordinator', args=[self.employee.id]),
            data=json.dumps({'coordinator': True}),
            content_type='application/json',
            HTTP_X_CSRFTOKEN='dummy'
        )
        self.employee.refresh_from_db()
        self.assertFalse(self.employee.coordinator,
            'FAIL #2: Employee promoted themselves to coordinator!')


# Issue #3 — Subscription Tenant Isolation
class TestIssue3SubscriptionIsolation(BaseTestCase):

    def test_subscription_has_company_field(self):
        """ISSUE #3: Subscription model must have company field"""
        self.assertTrue(hasattr(Subscription, 'company'),
            'FAIL #3: Subscription has no company field!')

    def test_coordinator_sees_only_own_company(self):
        """ISSUE #3: Coordinator sees only their company subscriptions"""
        self.client.login(username='coord@test.com',
                          password='Coord@1234#')
        r = self.client.get(reverse('subscriptions'))
        self.assertEqual(r.status_code, 200)
        content = r.content.decode()
        self.assertNotIn('Customer Beta', content,
            'FAIL #3: CompanyB subscription visible to CompanyA!')
        self.assertIn('Customer Alpha', content,
            'FAIL #3: CompanyA subscription not visible!')

    def test_new_subscription_gets_company(self):
        """ISSUE #3: New subscription auto-assigns company"""
        self.client.login(username='coord@test.com',
                          password='Coord@1234#')
        self.client.post(reverse('add_subscription'), {
            'subscription_type': 'netflix',
            'description': 'Test new sub',
            'ending_reminder': '1_week',
            'customer_name': 'New Cust',
            'customer_email': 'newcust@test.com',
            'customer_phone': '9000000099',
            'end_date': (timezone.now() + timedelta(days=30))
                         .strftime('%Y-%m-%dT%H:%M'),
        })
        sub = Subscription.objects.filter(
            customer_email='newcust@test.com'
        ).first()
        self.assertIsNotNone(sub, 'FAIL #3: Subscription not created!')
        self.assertEqual(sub.company, 'CompanyA',
            f'FAIL #3: company={sub.company}, expected CompanyA!')


# Issue #8 — datetime.now() default bug
class TestIssue8DateDefault(BaseTestCase):

    def test_submission_date_default_callable(self):
        """ISSUE #8: submission_date default must be callable"""
        field = Task._meta.get_field('submission_date')
        self.assertTrue(callable(field.default),
            'FAIL #8: default=datetime.now() — evaluated once at startup!')


# Issue #9 — DB Level Filtering
class TestIssue9DBFiltering(BaseTestCase):

    def test_summary_excludes_other_company(self):
        """ISSUE #9: Summary report must not show other company tasks"""
        self.client.login(username='coord@test.com',
                          password='Coord@1234#')
        r = self.client.get(reverse('summary_report'), {
            'date': date.today().strftime('%Y-%m-%d'),
            'filter': 'monthly'
        })
        content = r.content.decode()
        self.assertNotIn('Task Beta CompanyB', content,
            'FAIL #9: CompanyB task in CompanyA summary report!')

    def test_get_filtered_tasks_helper_exists(self):
        """ISSUE #9: get_filtered_tasks helper must exist"""
        from MITR_app import views
        self.assertTrue(hasattr(views, 'get_filtered_tasks'),
            'FAIL #9: get_filtered_tasks not in views.py!')

    def test_tasks_ordered_newest_first(self):
        """ISSUE #9: Tasks must be ordered by date_added desc"""
        from MITR_app import views
        if not hasattr(views, 'get_filtered_tasks'):
            self.skipTest('get_filtered_tasks not implemented yet')
        tasks = list(views.get_filtered_tasks('CompanyA'))
        dates = [t.date_added for t in tasks]
        self.assertEqual(dates, sorted(dates, reverse=True),
            'FAIL #9: Tasks not ordered newest first!')


# Issue #10 — Matplotlib Disk Writes
class TestIssue10Charts(BaseTestCase):

    def test_progress_page_no_png_written(self):
        """ISSUE #10: Employee progress must not write PNG to disk"""
        from pathlib import Path
        self.client.login(username='admin@test.com',
                          password='Admin@1234#')
        media_dir = Path('media/progress')
        before = set(media_dir.glob('*.png')) if media_dir.exists() else set()
        self.client.get(
            reverse('employee_progress', args=[self.employee.id])
        )
        after = set(media_dir.glob('*.png')) if media_dir.exists() else set()
        new_files = after - before
        self.assertEqual(len(new_files), 0,
            f'FAIL #10: PNG written to disk: {new_files}')

    def test_progress_context_has_counts(self):
        """ISSUE #10: Context must have total/completed/overdue/pending"""
        self.client.login(username='admin@test.com',
                          password='Admin@1234#')
        r = self.client.get(
            reverse('employee_progress', args=[self.employee.id])
        )
        self.assertEqual(r.status_code, 200)
        for key in ['total', 'completed', 'overdue', 'pending']:
            self.assertIn(key, r.context,
                f'FAIL #10: "{key}" missing from template context!')


# RBAC Tests
class TestRBAC(BaseTestCase):

    def test_employee_sees_only_own_tasks(self):
        """RBAC: Employee sees only their own tasks"""
        self.client.login(username='emp@test.com',
                          password='Emp@1234#')
        r = self.client.get(reverse('dashboard'))
        self.assertEqual(r.status_code, 200)
        for task in r.context.get('tasks', []):
            self.assertEqual(task.employee, self.employee,
                f'FAIL RBAC: Employee sees task of {task.employee}!')

    def test_employee_blocked_from_employee_list(self):
        """RBAC: Employee cannot access employee management"""
        self.client.login(username='emp@test.com',
                          password='Emp@1234#')
        r = self.client.get(reverse('employee_list'))
        self.assertNotEqual(r.status_code, 200,
            'FAIL RBAC: Employee can access Employee Management!')

    def test_employee_blocked_from_summary_report(self):
        """RBAC: Employee cannot access summary report"""
        self.client.login(username='emp@test.com',
                          password='Emp@1234#')
        r = self.client.get(reverse('summary_report'))
        self.assertNotEqual(r.status_code, 200,
            'FAIL RBAC: Employee can access Summary Report!')

    def test_employee_blocked_from_subscriptions(self):
        """RBAC: Employee cannot access subscriptions"""
        self.client.login(username='emp@test.com',
                          password='Emp@1234#')
        r = self.client.get(reverse('subscriptions'))
        self.assertNotEqual(r.status_code, 200,
            'FAIL RBAC: Employee can access Subscriptions!')

    def test_coordinator_cannot_add_employee(self):
        """RBAC: Coordinator cannot add employees"""
        self.client.login(username='coord@test.com',
                          password='Coord@1234#')
        r = self.client.get(reverse('add_employee'))
        self.assertNotEqual(r.status_code, 200,
            'FAIL RBAC: Coordinator can access Add Employee!')

    def test_admin_full_access(self):
        """RBAC: Admin can access everything"""
        self.client.login(username='admin@test.com',
                          password='Admin@1234#')
        pages = ['dashboard', 'employee_list',
                 'summary_report', 'subscriptions']
        for page in pages:
            r = self.client.get(reverse(page))
            self.assertEqual(r.status_code, 200,
                f'FAIL RBAC: Admin blocked from {page}!')

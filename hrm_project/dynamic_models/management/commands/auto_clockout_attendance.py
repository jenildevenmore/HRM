from datetime import date

from django.conf import settings
from django.core.mail import send_mail
from django.core.management.base import BaseCommand

from dynamic_models.models import DynamicRecord


class Command(BaseCommand):
    help = (
        "Auto clock-out missed attendance records. "
        "If check_in exists and check_out is missing for a past date, set check_out to 23:59:59 "
        "and notify assigned HR/Manager via email."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Preview records that would be auto clocked-out without saving changes.',
        )
        parser.add_argument(
            '--no-email',
            action='store_true',
            help='Skip email notifications.',
        )

    def handle(self, *args, **options):
        dry_run = bool(options.get('dry_run'))
        no_email = bool(options.get('no_email'))
        today = date.today()
        today_iso = today.isoformat()

        qs = (
            DynamicRecord.objects.select_related(
                'dynamic_model',
                'dynamic_model__client',
                'employee',
                'employee__manager',
                'employee__hr',
            )
            .filter(dynamic_model__slug='attendance')
            .order_by('id')
        )

        processed = 0
        updated = 0
        emailed = 0
        skipped = 0

        for record in qs.iterator():
            processed += 1
            data = dict(record.data or {})
            attendance_date_raw = str(data.get('attendance_date') or '').strip()
            check_in = str(data.get('check_in') or '').strip()
            check_out = str(data.get('check_out') or '').strip()

            if not attendance_date_raw or not check_in:
                skipped += 1
                continue
            if check_out:
                skipped += 1
                continue
            if attendance_date_raw >= today_iso:
                # Today's open attendance should not be auto-closed yet.
                skipped += 1
                continue

            try:
                attendance_date = date.fromisoformat(attendance_date_raw)
            except ValueError:
                skipped += 1
                continue

            auto_checkout_time = '23:59:59'
            remarks = str(data.get('remarks') or '').strip()
            auto_note = f'Auto clock-out by system at {auto_checkout_time} (missed punch-out).'
            data['check_out'] = auto_checkout_time
            data['remarks'] = f'{remarks} | {auto_note}' if remarks else auto_note
            record.data = data

            employee = record.employee
            employee_name = ''
            if employee:
                employee_name = f'{employee.first_name} {employee.last_name}'.strip()

            if dry_run:
                self.stdout.write(
                    self.style.WARNING(
                        f'[DRY RUN] Would auto clock-out record #{record.id} '
                        f'for {employee_name or "Employee"} on {attendance_date.isoformat()}'
                    )
                )
                updated += 1
                continue

            record.save(update_fields=['data', 'updated_at'])
            updated += 1

            if no_email:
                continue

            client_settings = {}
            try:
                client_settings = dict((record.dynamic_model.client.app_settings or {}))
            except Exception:
                client_settings = {}
            email_notification_settings = client_settings.get('email_notifications') or {}
            attendance_email_enabled = bool(email_notification_settings.get('attendance_alert_email', True))
            if not attendance_email_enabled:
                continue

            recipients = []
            if employee and employee.manager and employee.manager.email:
                recipients.append(employee.manager.email)
            if employee and employee.hr and employee.hr.email:
                recipients.append(employee.hr.email)
            recipients = sorted({str(e).strip().lower() for e in recipients if str(e).strip()})
            if not recipients:
                continue

            subject = f'Attendance Alert: Missed Punch-Out Auto-Closed ({attendance_date.isoformat()})'
            message = (
                f'Employee: {employee_name or "-"}\n'
                f'Employee Email: {(employee.email if employee else "-")}\n'
                f'Date: {attendance_date.isoformat()}\n'
                f'Check-In: {check_in}\n'
                f'Check-Out: {auto_checkout_time} (auto)\n\n'
                'Reason: Employee missed punch-out. System automatically closed attendance at end of day.'
            )
            send_mail(
                subject=subject,
                message=message,
                from_email=getattr(settings, 'DEFAULT_FROM_EMAIL', 'no-reply@example.com'),
                recipient_list=recipients,
                fail_silently=True,
            )
            emailed += 1

        mode = 'DRY RUN' if dry_run else 'LIVE'
        self.stdout.write(self.style.SUCCESS(f'[{mode}] Processed: {processed}'))
        self.stdout.write(self.style.SUCCESS(f'[{mode}] Auto clocked-out: {updated}'))
        self.stdout.write(self.style.SUCCESS(f'[{mode}] Email notifications sent: {emailed}'))
        self.stdout.write(self.style.SUCCESS(f'[{mode}] Skipped: {skipped}'))

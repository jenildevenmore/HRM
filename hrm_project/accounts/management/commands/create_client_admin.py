from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from accounts.models import UserProfile
from clients.models import Client


class Command(BaseCommand):
    help = 'Create a client admin user'

    def add_arguments(self, parser):
        parser.add_argument('--username', type=str, required=True, help='Username for the new admin')
        parser.add_argument('--password', type=str, required=True, help='Password for the new admin')
        parser.add_argument('--email', type=str, required=True, help='Email for the new admin')
        parser.add_argument('--client-id', type=int, required=True, help='Client ID for this admin')

    def handle(self, *args, **options):
        username = options['username']
        password = options['password']
        email = options['email']
        client_id = options['client_id']

        # Check if user already exists
        if User.objects.filter(username=username).exists():
            self.stdout.write(self.style.ERROR(f'User {username} already exists!'))
            return

        # Check if client exists
        try:
            client = Client.objects.get(id=client_id)
        except Client.DoesNotExist:
            self.stdout.write(self.style.ERROR(f'Client with ID {client_id} does not exist!'))
            return

        # Create user
        user = User.objects.create_user(
            username=username,
            email=email,
            password=password
        )

        # Create profile
        profile = UserProfile.objects.create(
            user=user,
            client=client,
            role='admin'
        )

        self.stdout.write(self.style.SUCCESS(f'Successfully created admin user {username} for client {client.name}'))

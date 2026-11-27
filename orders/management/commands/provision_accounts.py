import os

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from orders.access import APPROVER, CREATOR


class Command(BaseCommand):
    help = "Provision the four assignment accounts and their roles."

    @transaction.atomic
    def handle(self, *args, **options):
        accounts = {
            "creator1": [CREATOR],
            "creator2": [CREATOR],
            "approver1": [APPROVER],
            "lead1": [CREATOR, APPROVER],
        }
        groups = {name: Group.objects.get_or_create(name=name)[0] for name in (CREATOR, APPROVER)}
        for username, role_names in accounts.items():
            user, created = get_user_model().objects.get_or_create(username=username)
            if created:
                variable = f"{username.upper()}_PASSWORD"
                password = os.environ.get(variable)
                if not password:
                    raise CommandError(f"Set {variable} privately before provisioning new accounts.")
                user.set_password(password)
                user.save(update_fields=["password"])
            user.groups.set(groups[name] for name in role_names)
        self.stdout.write("Provisioned the four purchase-order accounts.")

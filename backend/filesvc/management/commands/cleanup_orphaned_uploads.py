from django.core.management.base import BaseCommand
from filesvc.service import file_service

class Command(BaseCommand):
    help = "Clean up uploaded files that were never attached to a message."

    def add_arguments(self, parser):
        parser.add_argument(
            "--hours",
            type=int,
            default=24,
            help="Age threshold in hours for orphaned files (default: 24)",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Simulate cleanup without deleting any files from disk or database",
        )

    def handle(self, *args, **options):
        hours = options["hours"]
        dry_run = options["dry_run"]

        self.stdout.write(f"Scanning for orphaned uploads older than {hours} hours (dry_run={dry_run})...")
        result = file_service.cleanup_orphaned_uploads(older_than_hours=hours, dry_run=dry_run)

        action = "Would delete" if dry_run else "Deleted"
        self.stdout.write(
            self.style.SUCCESS(
                f"{action} {result['count']} orphaned upload(s), freeing {result['bytes_freed']} bytes."
            )
        )

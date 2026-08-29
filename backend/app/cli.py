import argparse
import sys
from app.core.database import SessionLocal, Base, engine
from app.models.admin import Admin
from app.models import *  # import all models so Base has metadata
from app.services.auth_service import auth_service


def main():
    parser = argparse.ArgumentParser(description="SBK Quiz Analyzer Backend CLI")
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # init-db
    subparsers.add_parser("init-db", help="Initialize database tables")

    # create-admin
    create_admin_parser = subparsers.add_parser("create-admin", help="Create a new admin user")
    create_admin_parser.add_argument("--email", required=True, help="Admin email address")
    create_admin_parser.add_argument("--password", required=True, help="Admin password (min 8 chars)")
    create_admin_parser.add_argument("--role", default="ADMIN", help="Role (default: ADMIN)")

    # list-admins
    subparsers.add_parser("list-admins", help="List all administrator accounts")

    # reset-password
    reset_pwd_parser = subparsers.add_parser("reset-password", help="Reset an admin's password")
    reset_pwd_parser.add_argument("--email", required=True, help="Admin email address")
    reset_pwd_parser.add_argument("--password", required=True, help="New admin password")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    # Ensure tables exist
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()

    try:
        if args.command == "init-db":
            print("[SUCCESS] Database schema initialized successfully.")

        elif args.command == "create-admin":
            if len(args.password) < 8:
                print("[ERROR] Password must be at least 8 characters.")
                sys.exit(1)
            try:
                admin = auth_service.create_admin(
                    db,
                    email=args.email,
                    password=args.password,
                    role=args.role,
                )
                print(f"[SUCCESS] Admin user '{admin.email}' (ID: {admin.id}, Role: {admin.role}) created successfully.")
            except ValueError as e:
                print(f"[ERROR] Error creating admin: {e}")
                sys.exit(1)

        elif args.command == "list-admins":
            admins = db.query(Admin).order_by(Admin.id.asc()).all()
            print(f"Total Admins: {len(admins)}")
            print("-" * 60)
            for a in admins:
                status_str = "ACTIVE" if a.is_active else "DISABLED"
                print(f"ID: {a.id:<4} | Email: {a.email:<25} | Role: {a.role:<8} | Status: {status_str}")

        elif args.command == "reset-password":
            admin = auth_service.get_admin_by_email(db, args.email)
            if not admin:
                print(f"[ERROR] No admin found with email '{args.email}'")
                sys.exit(1)
            from app.core.security import hash_password
            admin.password_hash = hash_password(args.password)
            db.commit()
            print(f"[SUCCESS] Password for admin '{admin.email}' reset successfully.")

    finally:
        db.close()


if __name__ == "__main__":
    main()

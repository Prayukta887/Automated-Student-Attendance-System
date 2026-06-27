import unittest
from app import app, db, User, bcrypt, Subject, Session, Attendance, get_ist_time
from datetime import timedelta


class TestApp(unittest.TestCase):

    def setUp(self):
        app.config['TESTING'] = True
        app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'

        self.app = app.test_client()

        # Push app context
        self.app_context = app.app_context()
        self.app_context.push()

        db.create_all()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.app_context.pop()

    # ============================
    # UNIT TESTING
    # ============================

    def test_user_creation(self):
        user = User(username="test", password="123", role="student")
        db.session.add(user)
        db.session.commit()

        self.assertEqual(User.query.count(), 1)

    def test_attendance_calculation(self):
        present = 15
        total = 20
        percentage = (present / total) * 100

        self.assertEqual(percentage, 75.0)

    def test_password_hashing(self):
        password = "123"
        hashed = bcrypt.generate_password_hash(password).decode('utf-8')

        self.assertTrue(bcrypt.check_password_hash(hashed, password))

    # ============================
    # SECURITY TESTING
    # ============================

    def test_invalid_login(self):
        response = self.app.post('/login', data={
            'username': 'wrong',
            'password': 'wrong'
        })

        self.assertNotEqual(response.status_code, 302)

    def test_sql_injection(self):
        response = self.app.post('/login', data={
            'username': "' OR '1'='1",
            'password': "anything"
        })

        self.assertNotEqual(response.status_code, 302)

    def test_unauthorized_access(self):
        response = self.app.post('/mark_attendance', json={"session_code": "x"})
        self.assertNotEqual(response.status_code, 200)

    def test_session_security(self):
        self.assertTrue(app.config['SESSION_COOKIE_SECURE'])

    def test_invalid_qr(self):
        hashed_password = bcrypt.generate_password_hash("123").decode('utf-8')

    # Create student
        user = User(
            username="student",
            password=hashed_password,
            role="student",
            year=1,
            semester=1,
            division="A"
        )
        db.session.add(user)
        db.session.commit()

        with self.app:
        # ✅ login first
            self.app.post('/login', data={
                'username': 'student',
                'password': '123'
         })

        # ❌ invalid QR
            response = self.app.post(
                '/mark_attendance',
                json={"session_code": "wrong"}
            )

            self.assertIn(b'Invalid', response.data)
    # ============================
    # INTEGRATION TESTING
    # ============================

    def test_integration_login_to_attendance(self):
        hashed_password = bcrypt.generate_password_hash("123").decode('utf-8')

        # Create student
        user = User(
            username="student",
            password=hashed_password,
            role="student",
            year=1,
            semester=1,
            division="A"
        )
        db.session.add(user)
        db.session.commit()

        # Create subject
        subject = Subject(
            subject="Math",
            year=1,
            semester=1,
            division="A",
            faculty_id=None
        )
        db.session.add(subject)
        db.session.commit()

        # Create session
        session_obj = Session(
            session_code="test123",
            subject_id=subject.id,
            expires_at=get_ist_time() + timedelta(minutes=10),
            year=1,
            semester=1,
            division="A"
        )
        db.session.add(session_obj)
        db.session.commit()

        with self.app:
            # login
            self.app.post('/login', data={
                'username': 'student',
                'password': '123'
            })

            # mark attendance
            response = self.app.post(
                '/mark_attendance',
                json={"session_code": "test123"}
            )

            self.assertEqual(response.status_code, 200)

    def test_integration_db_flow(self):
        user = User(username="test", password="123", role="student")
        db.session.add(user)
        db.session.commit()

        fetched = User.query.filter_by(username="test").first()
        self.assertIsNotNone(fetched)

    # ============================
    # SYSTEM TESTING
    # ============================

    def test_system_full_flow(self):
        hashed_password = bcrypt.generate_password_hash("123").decode('utf-8')

        # Create student
        user = User(
            username="student",
            password=hashed_password,
            role="student",
            year=1,
            semester=1,
            division="A"
        )
        db.session.add(user)
        db.session.commit()

        # Create subject
        subject = Subject(
            subject="Science",
            year=1,
            semester=1,
            division="A",
            faculty_id=None
        )
        db.session.add(subject)
        db.session.commit()

        # Create session
        session_obj = Session(
            session_code="system123",
            subject_id=subject.id,
            expires_at=get_ist_time() + timedelta(minutes=10),
            year=1,
            semester=1,
            division="A"
        )
        db.session.add(session_obj)
        db.session.commit()

        with self.app:
            # Step 1: Login
            login_response = self.app.post('/login', data={
                'username': 'student',
                'password': '123'
            })
            self.assertEqual(login_response.status_code, 302)

            # Step 2: Mark attendance
            attend_response = self.app.post(
                '/mark_attendance',
                json={"session_code": "system123"}
            )
            self.assertEqual(attend_response.status_code, 200)

            # Step 3: Verify DB
            records = Attendance.query.all()
            self.assertTrue(len(records) > 0)


if __name__ == '__main__':
    unittest.main()
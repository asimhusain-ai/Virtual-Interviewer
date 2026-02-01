# Unit tests for app.py
import unittest
from unittest.mock import patch
import sys
import os
import json
import time
import string
from datetime import datetime, timedelta

from flask import session

# Add parent directory to path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import (
    app,
    user_sessions,
    db,
    User,
    UserMeta,
    Profile,
    ProfileMedia,
    Result,
    calculate_points,
    _build_leaderboard,
    _safe_env_int,
    _normalize_difficulty_label,
    _coerce_percentage,
    _extract_difficulty_from_details,
    _aggregate_points_for_users,
    _is_session_expired,
    _cleanup_sessions,
    _start_user_session,
    _get_or_create_oauth_user,
    _generate_unique_username,
    _sanitize_username,
    _find_user_by_login_identifier,
    _username_taken,
    _generate_temp_password,
    SESSION_TTL_SECONDS,
)
import io
import uuid


class TestFlaskApp(unittest.TestCase):
    """Test cases for Flask application endpoints"""
    
    def setUp(self):
        """Set up test client and clear sessions before each test"""
        self.app = app
        self.app.config['TESTING'] = True
        self.client = self.app.test_client()
        user_sessions.clear()
        # Ensure 'details' column exists on result table for legacy DBs
        with self.app.app_context():
            try:
                res = db.engine.execute("PRAGMA table_info('result')").fetchall()
                cols = [r[1] for r in res]
                if 'details' not in cols:
                    try:
                        db.engine.execute("ALTER TABLE result ADD COLUMN details TEXT")
                    except Exception:
                        pass
            except Exception:
                pass
    
    def tearDown(self):
        """Clean up after each test"""
        user_sessions.clear()
        # Clean test uploads if any
        uploads = os.path.join(app.root_path, 'static', 'uploads')
        if os.path.isdir(uploads):
            try:
                for f in os.listdir(uploads):
                    if f.startswith('user_'):
                        try:
                            os.remove(os.path.join(uploads, f))
                        except Exception:
                            pass
            except Exception:
                pass
    
    def test_index_route(self):
        """Test that index route returns HTML"""
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)

    def test_logout_sets_no_cache_and_clear_site_data(self):
        """Logout should clear cache and prevent back navigation."""
        response = self.client.get('/logout', follow_redirects=False)
        self.assertEqual(response.status_code, 302)
        self.assertIn('logged_out=1', response.headers.get('Location', ''))
        self.assertIn('no-store', response.headers.get('Cache-Control', ''))
        self.assertEqual(response.headers.get('Pragma'), 'no-cache')
        self.assertEqual(response.headers.get('Expires'), '0')
        self.assertIn('Clear-Site-Data', response.headers)

    def test_protected_route_has_no_cache_headers(self):
        """Protected routes should send no-store headers even when redirected."""
        response = self.client.get('/dashboard', follow_redirects=False)
        self.assertEqual(response.status_code, 302)
        self.assertIn('no-store', response.headers.get('Cache-Control', ''))
    
    @patch('app.fetch_unique_interview_questions')
    def test_start_interview_success(self, mock_fetch):
        """Test successful interview start"""
        mock_fetch.return_value = ["What is Python?", "Explain OOP?"]
        
        response = self.client.post('/api/start_interview',
                                   json={
                                       'role': 'Technical',
                                       'limit': 2,
                                       'difficulty': 'Easy'
                                   })
        
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        
        self.assertTrue(data['success'])
        self.assertIn('session_id', data)
        self.assertIn('questions', data)
        self.assertEqual(len(data['questions']), 2)
        self.assertIn('current_question', data)
    
    @patch('app.fetch_unique_interview_questions')
    def test_start_interview_default_values(self, mock_fetch):
        """Test interview start with default values"""
        mock_fetch.return_value = ["What is Python?"]
        
        response = self.client.post('/api/start_interview', json={})
        
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        
        self.assertTrue(data['success'])
        self.assertIn('session_id', data)
    
    @patch('app.fetch_unique_interview_questions')
    def test_start_interview_error_handling(self, mock_fetch):
        """Test error handling when starting interview"""
        mock_fetch.side_effect = Exception("API Error")
        
        response = self.client.post('/api/start_interview',
                                   json={'role': 'Technical'})
        
        self.assertEqual(response.status_code, 500)
        data = json.loads(response.data)
        
        self.assertFalse(data['success'])
        self.assertIn('error', data)
    
    @patch('app.evaluate_answer')
    @patch('app.analyze_tone')
    def test_submit_answer_success(self, mock_tone, mock_eval):
        """Test successful answer submission"""
        # Set up mocks
        mock_eval.return_value = {
            'feedback': 'Good answer',
            'score': 85,
            'expected_answer': 'A programming language'
        }
        mock_tone.return_value = {
            'tone': 'Confident'
        }
        
        # Create a session
        session_id = 'test-session-123'
        user_sessions[session_id] = {
            'role': 'Technical',
            'limit': 2,
            'difficulty': 'Easy',
            'questions': ['What is Python?', 'What is OOP?'],
            'current_index': 0,
            'answers': [],
            'feedbacks': [],
            'scores': [],
            'tones': [],
            'expected_answers': [],
            'show_answer_warning': False,
            'is_submitting': False
        }
        
        response = self.client.post('/api/submit_answer',
                                   json={
                                       'session_id': session_id,
                                       'answer': 'Python is a programming language'
                                   })
        
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        
        self.assertTrue(data['success'])
        self.assertIn('feedback', data)
        self.assertIn('score', data)
        self.assertIn('tone', data)
        self.assertIn('expected_answer', data)
        self.assertIn('is_complete', data)
        self.assertIn('progress', data)
    
    def test_submit_answer_invalid_session(self):
        """Test answer submission with invalid session"""
        response = self.client.post('/api/submit_answer',
                                   json={
                                       'session_id': 'invalid-session',
                                       'answer': 'Test answer'
                                   })
        
        self.assertEqual(response.status_code, 404)
        data = json.loads(response.data)
        
        self.assertFalse(data['success'])
        self.assertIn('error', data)
    
    @patch('app.evaluate_answer')
    @patch('app.analyze_tone')
    def test_submit_answer_complete_interview(self, mock_tone, mock_eval):
        """Test completing interview with final answer"""
        mock_eval.return_value = {
            'feedback': 'Good answer',
            'score': 85,
            'expected_answer': 'A programming language'
        }
        mock_tone.return_value = {
            'tone': 'Confident'
        }
        
        # Create a session with only one question
        session_id = 'test-session-complete'
        user_sessions[session_id] = {
            'role': 'Technical',
            'limit': 1,
            'difficulty': 'Easy',
            'questions': ['What is Python?'],
            'current_index': 0,
            'answers': [],
            'feedbacks': [],
            'scores': [],
            'tones': [],
            'expected_answers': [],
            'show_answer_warning': False,
            'is_submitting': False
        }
        
        response = self.client.post('/api/submit_answer',
                                   json={
                                       'session_id': session_id,
                                       'answer': 'Python is a programming language'
                                   })
        
        data = json.loads(response.data)
        
        self.assertTrue(data['is_complete'])
        self.assertIsNone(data['next_question'])
    
    @patch('app.evaluate_answer')
    @patch('app.analyze_tone')
    def test_submit_answer_error_handling(self, mock_tone, mock_eval):
        """Test error handling during answer submission"""
        mock_eval.side_effect = Exception("Evaluation error")
        
        session_id = 'test-session-error'
        user_sessions[session_id] = {
            'role': 'Technical',
            'limit': 1,
            'difficulty': 'Easy',
            'questions': ['What is Python?'],
            'current_index': 0,
            'answers': [],
            'feedbacks': [],
            'scores': [],
            'tones': [],
            'expected_answers': [],
            'show_answer_warning': False,
            'is_submitting': False
        }
        
        response = self.client.post('/api/submit_answer',
                                   json={
                                       'session_id': session_id,
                                       'answer': 'Python is a programming language'
                                   })
        
        self.assertEqual(response.status_code, 500)
        data = json.loads(response.data)
        self.assertFalse(data['success'])
    
    def test_get_question_success(self):
        """Test retrieving a specific question"""
        session_id = 'test-session-get'
        user_sessions[session_id] = {
            'questions': ['Question 1?', 'Question 2?']
        }
        
        response = self.client.get(f'/api/get_question/{session_id}/0')
        
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        
        self.assertTrue(data['success'])
        self.assertEqual(data['question'], 'Question 1?')
    
    def test_get_question_invalid_session(self):
        """Test retrieving question with invalid session"""
        response = self.client.get('/api/get_question/invalid-session/0')
        
        self.assertEqual(response.status_code, 404)
        data = json.loads(response.data)
        
        self.assertFalse(data['success'])
        self.assertIn('error', data)
    
    def test_get_question_invalid_index(self):
        """Test retrieving question with invalid index"""
        session_id = 'test-session-invalid-index'
        user_sessions[session_id] = {
            'questions': ['Question 1?']
        }
        
        response = self.client.get(f'/api/get_question/{session_id}/5')
        
        self.assertEqual(response.status_code, 404)
        data = json.loads(response.data)
        
        self.assertFalse(data['success'])
    
    def test_get_session_success(self):
        """Test retrieving session data"""
        session_id = 'test-session-retrieve'
        session_data = {
            'role': 'Technical',
            'limit': 2,
            'questions': ['Q1?', 'Q2?']
        }
        user_sessions[session_id] = session_data
        
        response = self.client.get(f'/api/session/{session_id}')
        
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        
        self.assertTrue(data['success'])
        self.assertIn('session', data)
        self.assertEqual(data['session']['role'], 'Technical')
    
    def test_get_session_not_found(self):
        """Test retrieving non-existent session"""
        response = self.client.get('/api/session/non-existent-session')
        
        self.assertEqual(response.status_code, 404)
        data = json.loads(response.data)
        
        self.assertFalse(data['success'])
        self.assertIn('error', data)
    
    def test_end_session_success(self):
        """Test ending a session successfully"""
        session_id = 'test-session-end'
        user_sessions[session_id] = {
            'role': 'Technical'
        }
        
        response = self.client.delete(f'/api/end_session/{session_id}')
        
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        
        self.assertTrue(data['success'])
        self.assertNotIn(session_id, user_sessions)
    
    def test_end_session_not_found(self):
        """Test ending non-existent session"""
        response = self.client.delete('/api/end_session/non-existent-session')
        
        self.assertEqual(response.status_code, 404)
        data = json.loads(response.data)
        
        self.assertFalse(data['success'])
        self.assertIn('error', data)

    # ---------------- Results tests ----------------
    def test_results_requires_auth(self):
        r = self.client.get('/api/results')
        self.assertEqual(r.status_code, 401)

    @patch('app.fetch_unique_interview_questions')
    @patch('app.evaluate_answer')
    @patch('app.analyze_tone')
    def test_results_returns_user_rows(self, mock_tone, mock_eval, mock_fetch):
        uid = self._create_user_and_login()
        # Prepare mocks
        mock_fetch.return_value = ["What is Python?"]
        mock_eval.return_value = { 'feedback': 'ok', 'score': 88, 'expected_answer': 'A language' }
        mock_tone.return_value = { 'tone': 'Neutral' }

        # Start interview
        start = self.client.post('/api/start_interview', json={'role':'Technical','limit':1,'difficulty':'Easy'})
        self.assertEqual(start.status_code, 200)
        sid = json.loads(start.data)['session_id']

        # Submit answer (will persist result)
        submit = self.client.post('/api/submit_answer', json={'session_id': sid, 'answer': 'test'})
        self.assertEqual(submit.status_code, 200)

        # Fetch results
        resp = self.client.get('/api/results')
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.data)
        self.assertTrue(data['success'])
        self.assertGreaterEqual(len(data['results']), 1)
        self.assertIn('date', data['results'][0])
        self.assertIn('time', data['results'][0])

    # ---------------- Profile tests ----------------
    def test_profile_requires_auth(self):
        r1 = self.client.get('/api/profile')
        self.assertEqual(r1.status_code, 401)
        r2 = self.client.post('/api/profile', json={})
        self.assertEqual(r2.status_code, 401)

    def test_oauth_route_redirects_or_external(self):
        response = self.client.get('/auth/google')
        self.assertEqual(response.status_code, 302)
        target = response.headers.get('Location', '')
        self.assertTrue(target, 'Expected redirect location to be present')
        if '/login' not in target:
            self.assertTrue(target.startswith('https://accounts.google.com/'))

    def test_oauth_callback_redirects_when_unconfigured(self):
        response = self.client.get('/auth/google/callback')
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login', response.headers.get('Location', ''))

    def test_calculate_points_multipliers(self):
        self.assertEqual(calculate_points('quiz', 70, 'Beginner'), 7)
        self.assertEqual(calculate_points('quiz', 70, 'Intermediate'), 14)
        self.assertEqual(calculate_points('quiz', 70, 'Professional'), 21)
        self.assertEqual(calculate_points('ai', 99, 'Professional'), 27)
        self.assertEqual(calculate_points('ai', '85%', 'Hard'), 24)
        self.assertEqual(calculate_points('quiz', '09%', 'Medium'), 0)

    def test_leaderboard_orders_by_points(self):
        with self.app.app_context():
            email_one = f"points_user_{uuid.uuid4().hex[:6]}@example.com"
            email_two = f"points_user_{uuid.uuid4().hex[6:12]}@example.com"
            user_one = User(name='Beginner Points', email=email_one, password_hash='x')
            user_two = User(name='Pro Points', email=email_two, password_hash='y')
            db.session.add_all([user_one, user_two])
            db.session.flush()

            beginner_details = json.dumps({'difficulty': 'Beginner'})
            pro_details = json.dumps({'difficulty': 'Professional'})
            res_one = Result(user_id=user_one.id, title='Quiz Beginner', score=95, kind='quiz', details=beginner_details)
            res_two = Result(user_id=user_two.id, title='Interview Pro', score=70, kind='interview', details=pro_details)
            db.session.add_all([res_one, res_two])
            db.session.commit()

            with patch('app._get_excluded_user_ids', return_value=set()):
                with self.app.test_request_context('/'):
                    entries = _build_leaderboard(limit=1000)
            filtered = {e['user_id']: e for e in entries if e['user_id'] in {user_one.id, user_two.id}}
            self.assertEqual(len(filtered), 2)
            self.assertGreater(filtered[user_two.id]['points_total'], filtered[user_one.id]['points_total'])
            self.assertEqual(filtered[user_two.id]['points_total'], 21)
            self.assertEqual(filtered[user_one.id]['points_total'], 9)
            self.assertLess(filtered[user_two.id]['rank'], filtered[user_one.id]['rank'])

            Result.query.filter(Result.user_id.in_([user_one.id, user_two.id])).delete(synchronize_session=False)
            db.session.delete(user_one)
            db.session.delete(user_two)
            db.session.commit()

    def _create_user_and_login(self):
        with app.app_context():
            # ensure unique email
            unique_email = f"testuser_{uuid.uuid4().hex[:8]}@example.com"
            u = User(name='Test User', email=unique_email, password_hash='x')
            db.session.add(u)
            db.session.commit()
            uid = u.id
        with self.client.session_transaction() as sess:
            sess['user_id'] = uid
            sess['user_email'] = unique_email
        return uid

    def test_profile_get_post_cycle(self):
        uid = self._create_user_and_login()
        # initial GET should succeed
        r = self.client.get('/api/profile')
        self.assertEqual(r.status_code, 200)
        data = json.loads(r.data)
        self.assertTrue(data['success'])
        # POST update
        unique_username = f"newuser{uuid.uuid4().hex[:6]}"
        payload = {
            'name': 'New Name',
            'username': unique_username,
            'bio': 'Hello there',
            'university': 'Test Univ',
            'location': 'City',
            'website': 'https://example.com',
            'linkedin': 'https://linkedin.com/in/new',
            'github': 'https://github.com/new',
            'pronouns': 'they/them',
        }
        r2 = self.client.post('/api/profile', json=payload)
        self.assertEqual(r2.status_code, 200)
        d2 = json.loads(r2.data)
        self.assertTrue(d2['success'])
        # GET again and verify
        r3 = self.client.get('/api/profile')
        prof = json.loads(r3.data)['profile']
        self.assertEqual(prof['name'], 'New Name')
        self.assertEqual(prof['username'], unique_username)
        self.assertEqual(prof['bio'], 'Hello there')
        self.assertEqual(prof['university'], 'Test Univ')
        self.assertEqual(prof['location'], 'City')
        self.assertEqual(prof['website'], 'https://example.com')
        self.assertEqual(prof['linkedin'], 'https://linkedin.com/in/new')
        self.assertEqual(prof['github'], 'https://github.com/new')
        self.assertEqual(prof['pronouns'], 'they/them')

    def test_profile_picture_upload_delete(self):
        uid = self._create_user_and_login()
        # upload
        data = {
            'file': (io.BytesIO(b'fake-image-bytes'), 'avatar.png', 'image/png')
        }
        r = self.client.post('/api/profile_picture', data=data, content_type='multipart/form-data')
        self.assertEqual(r.status_code, 200)
        d = json.loads(r.data)
        self.assertTrue(d['success'])
        self.assertEqual(d['path'], f"media/profile/{uid}")
        self.assertIn('url', d)
        self.assertIn(f"/media/profile/{uid}", d['url'])
        with self.app.app_context():
            media = ProfileMedia.query.filter_by(user_id=uid).first()
            self.assertIsNotNone(media)
            self.assertTrue(media.data)
            meta = UserMeta.query.filter_by(user_id=uid).first()
            self.assertEqual(meta.profile_pic, f"media/profile/{uid}")
        media_resp = self.client.get(f'/media/profile/{uid}')
        self.assertEqual(media_resp.status_code, 200)
        self.assertEqual(media_resp.mimetype, 'image/png')
        self.assertEqual(media_resp.data, b'fake-image-bytes')
        # delete
        r2 = self.client.delete('/api/profile_picture')
        self.assertEqual(r2.status_code, 200)
        d2 = json.loads(r2.data)
        self.assertTrue(d2['success'])
        with self.app.app_context():
            self.assertIsNone(ProfileMedia.query.filter_by(user_id=uid).first())
            meta = UserMeta.query.filter_by(user_id=uid).first()
            self.assertIsNone(meta.profile_pic)

    def test_quiz_result_persists_and_listed(self):
        uid = self._create_user_and_login()
        payload = {
            'role': 'Aptitude',
            'difficulty': 'Medium',
            'score': 3,
            'total': 5,
            'selections': ['A','B','C','D','E'],
            'questions': [
                {'question':'Q1','correct_answer':'A','options':['A','B','C','D']},
                {'question':'Q2','correct_answer':'B','options':['A','B','C','D']}
            ]
        }
        resp = self.client.post('/api/save_quiz_result', json=payload)
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.data)
        self.assertTrue(data['success'])
        # Then results should include at least one Quiz entry
        r = self.client.get('/api/results')
        self.assertEqual(r.status_code, 200)
        out = json.loads(r.data)
        kinds = [row['type'] for row in out['results']]
        self.assertIn('Quiz', kinds)


class TestSessionManagement(unittest.TestCase):
    """Test cases for session management"""
    
    def setUp(self):
        """Set up test client and clear sessions"""
        self.app = app
        self.app.config['TESTING'] = True
        self.client = self.app.test_client()
        user_sessions.clear()
    
    def tearDown(self):
        """Clean up after tests"""
        user_sessions.clear()
    
    def test_session_persistence(self):
        """Test that session data persists across requests"""
        session_id = 'test-persist'
        user_sessions[session_id] = {
            'role': 'HR',
            'limit': 5,
            'questions': ['Q1?', 'Q2?', 'Q3?', 'Q4?', 'Q5?']
        }
        
        # First request
        response1 = self.client.get(f'/api/session/{session_id}')
        data1 = json.loads(response1.data)
        
        # Second request
        response2 = self.client.get(f'/api/session/{session_id}')
        data2 = json.loads(response2.data)
        
        self.assertEqual(data1['session']['role'], data2['session']['role'])
        self.assertEqual(len(data1['session']['questions']), len(data2['session']['questions']))
    
    def test_multiple_sessions(self):
        """Test handling multiple concurrent sessions"""
        session1_id = 'session-1'
        session2_id = 'session-2'
        
        user_sessions[session1_id] = {'role': 'Technical'}
        user_sessions[session2_id] = {'role': 'HR'}
        
        response1 = self.client.get(f'/api/session/{session1_id}')
        response2 = self.client.get(f'/api/session/{session2_id}')
        
        data1 = json.loads(response1.data)
        data2 = json.loads(response2.data)
        
        self.assertEqual(data1['session']['role'], 'Technical')
        self.assertEqual(data2['session']['role'], 'HR')


class TestAppHelpers(unittest.TestCase):
    def setUp(self):
        self.app = app
        self.app.config['TESTING'] = True
        user_sessions.clear()

    def tearDown(self):
        user_sessions.clear()
        with self.app.app_context():
            db.session.rollback()

    def _cleanup_user(self, user_id):
        with self.app.app_context():
            Result.query.filter(Result.user_id == user_id).delete(synchronize_session=False)
            Profile.query.filter(Profile.user_id == user_id).delete(synchronize_session=False)
            UserMeta.query.filter(UserMeta.user_id == user_id).delete(synchronize_session=False)
            ProfileMedia.query.filter(ProfileMedia.user_id == user_id).delete(synchronize_session=False)
            db.session.query(User).filter(User.id == user_id).delete(synchronize_session=False)
            db.session.commit()

    def test_safe_env_int_handles_values(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(_safe_env_int('TEST_SAFE_INT', 9), 9)
        with patch.dict(os.environ, {'TEST_SAFE_INT': '42'}, clear=True):
            self.assertEqual(_safe_env_int('TEST_SAFE_INT', 9), 42)
        with patch.dict(os.environ, {'TEST_SAFE_INT': '-10'}, clear=True):
            self.assertEqual(_safe_env_int('TEST_SAFE_INT', 9), 9)
        with patch.dict(os.environ, {'TEST_SAFE_INT': 'not-int'}, clear=True):
            self.assertEqual(_safe_env_int('TEST_SAFE_INT', 9), 9)

    def test_normalize_difficulty_label_aliases(self):
        self.assertEqual(_normalize_difficulty_label('Easy'), 'beginner')
        self.assertEqual(_normalize_difficulty_label('Intermediate'), 'intermediate')
        self.assertEqual(_normalize_difficulty_label('Professional'), 'professional')
        self.assertEqual(_normalize_difficulty_label('Unknown'), 'beginner')
        self.assertEqual(_normalize_difficulty_label(None), 'beginner')

    def test_coerce_percentage_various_inputs(self):
        self.assertEqual(_coerce_percentage(85), 85.0)
        self.assertEqual(_coerce_percentage('95%'), 95.0)
        self.assertEqual(_coerce_percentage(' 70 '), 70.0)
        self.assertEqual(_coerce_percentage('abc'), 0.0)
        self.assertEqual(_coerce_percentage(120), 100.0)
        self.assertEqual(_coerce_percentage(-5), 0.0)
        self.assertEqual(_coerce_percentage(None), 0.0)

    def test_extract_difficulty_from_details_sources(self):
        self.assertEqual(_extract_difficulty_from_details({'difficulty': 'Pro'}), 'Pro')
        payload = json.dumps({'difficulty': 'Beginner'})
        self.assertEqual(_extract_difficulty_from_details(payload), 'Beginner')
        self.assertIsNone(_extract_difficulty_from_details('not-json'))
        self.assertIsNone(_extract_difficulty_from_details(None))

    def test_aggregate_points_for_users_computes_buckets(self):
        with self.app.app_context():
            email = f"agg_{uuid.uuid4().hex[:8]}@example.com"
            user = User(name='Agg Tester', email=email, password_hash='x')
            db.session.add(user)
            db.session.commit()
            user_id = user.id

            quiz_details = json.dumps({'difficulty': 'Professional'})
            ai_details = json.dumps({'difficulty': 'Beginner'})
            res_quiz = Result(user_id=user.id, title='Quiz', score=80, kind='quiz', details=quiz_details)
            res_ai = Result(user_id=user.id, title='Interview', score=90, kind='interview', details=ai_details)
            db.session.add_all([res_quiz, res_ai])
            db.session.commit()

            totals = _aggregate_points_for_users([user_id])
            self.assertIn(user_id, totals)
            expected_quiz = calculate_points('quiz', 80, 'Professional')
            expected_ai = calculate_points('ai', 90, 'Beginner')
            self.assertEqual(totals[user_id]['quiz'], expected_quiz)
            self.assertEqual(totals[user_id]['ai'], expected_ai)
            self.assertEqual(totals[user_id]['total'], expected_quiz + expected_ai)

        self._cleanup_user(user_id)

    def test_is_session_expired_checks_datetime_and_timestamp(self):
        old_dt = datetime.utcnow() - timedelta(seconds=SESSION_TTL_SECONDS + 5)
        recent_dt = datetime.utcnow()
        old_ts = time.time() - (SESSION_TTL_SECONDS + 5)
        self.assertTrue(_is_session_expired({'started_at': old_dt}))
        self.assertTrue(_is_session_expired({'started_at': old_ts}))
        self.assertFalse(_is_session_expired({'started_at': recent_dt}))
        self.assertFalse(_is_session_expired({'started_at': None}))

    def test_cleanup_sessions_removes_expired_sessions(self):
        expired_id = 'expired'
        active_id = 'active'
        user_sessions.clear()
        user_sessions[expired_id] = {
            'started_at': datetime.utcnow() - timedelta(seconds=SESSION_TTL_SECONDS + 10)
        }
        user_sessions[active_id] = {'started_at': datetime.utcnow()}

        _cleanup_sessions()

        self.assertNotIn(expired_id, user_sessions)
        self.assertIn(active_id, user_sessions)

    def test_generate_unique_username_adds_suffix_when_taken(self):
        with self.app.app_context():
            base_email = f"user_{uuid.uuid4().hex[:8]}@example.com"
            first_user = User(name='Original User', email=base_email, password_hash='x')
            db.session.add(first_user)
            db.session.commit()
            first_user_id = first_user.id
            profile = Profile(user_id=first_user.id, username='uniqueuser')
            db.session.add(profile)
            db.session.commit()

            candidate = _generate_unique_username('Unique User')
            self.assertNotEqual(candidate, 'uniqueuser')
            self.assertTrue(candidate.startswith('uniqueuser'))

        self._cleanup_user(first_user_id)

    def test_sanitize_username_filters_invalid_chars(self):
        self.assertEqual(_sanitize_username('User.Name '), 'username')
        self.assertEqual(_sanitize_username('USER-NAME123'), 'username123')
        self.assertIsNone(_sanitize_username('!!!'))

    def test_find_user_by_login_identifier_supports_email_and_username(self):
        with self.app.app_context():
            email = f"lookup_{uuid.uuid4().hex[:8]}@example.com"
            user = User(name='Lookup User', email=email, password_hash='x')
            db.session.add(user)
            db.session.commit()
            user_id = user.id
            username = 'lookupuser'
            profile = Profile(user_id=user.id, username=username)
            db.session.add(profile)
            db.session.commit()

            found_by_email = _find_user_by_login_identifier(email)
            self.assertIsNotNone(found_by_email)
            self.assertEqual(found_by_email.id, user_id)

            found_by_username = _find_user_by_login_identifier('LookupUser')
            self.assertIsNotNone(found_by_username)
            self.assertEqual(found_by_username.id, user_id)

        self._cleanup_user(user_id)

    def test_username_taken_respects_exclusion(self):
        with self.app.app_context():
            email = f"dup_{uuid.uuid4().hex[:8]}@example.com"
            user = User(name='Dup User', email=email, password_hash='x')
            db.session.add(user)
            db.session.commit()
            user_id = user.id
            username = 'duplicateuser'
            profile = Profile(user_id=user.id, username=username)
            db.session.add(profile)
            db.session.commit()

            self.assertTrue(_username_taken(username))
            self.assertFalse(_username_taken(username, exclude_user_id=user_id))

        self._cleanup_user(user_id)

    def test_generate_temp_password_respects_length_and_charset(self):
        password = _generate_temp_password(12)
        self.assertEqual(len(password), 12)
        allowed_chars = set(string.ascii_letters + string.digits)
        self.assertTrue(set(password) <= allowed_chars)

    def test_get_or_create_oauth_user_creates_and_reuses_user(self):
        with self.app.app_context():
            email = f"oauth_{uuid.uuid4().hex[:8]}@example.com"
            user, created = _get_or_create_oauth_user(
                email,
                'OAuth User',
                'google',
                'provider-123',
                avatar_url='https://example.com/avatar.png',
                birthdate='2000-01-01',
                location='Test City',
            )
            db.session.commit()
            user_id = user.id

            self.assertTrue(created)
            self.assertEqual(user.email, email)

            profile = Profile.query.filter_by(user_id=user_id).first()
            self.assertIsNotNone(profile)
            meta = UserMeta.query.filter_by(user_id=user_id).first()
            self.assertIsNotNone(meta)
            self.assertEqual(meta.profile_pic, 'https://example.com/avatar.png')
            self.assertEqual(meta.dob, '2000-01-01')
            self.assertEqual(profile.location, 'Test City')

            # Call again to ensure existing user is returned
            existing_user, created_again = _get_or_create_oauth_user(
                email,
                'Updated Name',
                'google',
                'provider-123',
                avatar_url='https://example.com/avatar.png',
            )
            db.session.commit()

            self.assertFalse(created_again)
            self.assertEqual(existing_user.id, user_id)

        self._cleanup_user(user_id)

    def test_start_user_session_populates_session_fields(self):
        with self.app.app_context():
            email = f"session_{uuid.uuid4().hex[:8]}@example.com"
            user = User(name='Session User', email=email, password_hash='x')
            db.session.add(user)
            db.session.commit()
            user_id = user.id
            profile = Profile(user_id=user.id, username='sessionuser', location='Profile City')
            meta = UserMeta(user_id=user.id, profile_pic='http://example.com/avatar.png', address='Meta City', dob='1999-12-31')
            db.session.add_all([profile, meta])
            db.session.commit()

            with self.app.test_request_context('/'):
                _start_user_session(user)
                self.assertEqual(session['user_id'], user.id)
                self.assertEqual(session['user_email'], email)
                self.assertEqual(session['user_name'], 'Session User')
                self.assertEqual(session['user_location'], 'Profile City')
                self.assertEqual(session['user_dob'], '1999-12-31')
                self.assertEqual(session['avatar_url'], 'http://example.com/avatar.png')

            self._cleanup_user(user_id)


if __name__ == '__main__':
    unittest.main()

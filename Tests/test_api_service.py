# Unit tests for services/api_service.py
import unittest
import json
from unittest.mock import patch, MagicMock, mock_open
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from services.api_service import (
    format_code_blocks,
    analyze_tone,
    evaluate_answer,
    fetch_interview_question,
    fetch_unique_interview_questions,
    _build_technical_prompts,
    _build_analytics_prompt,
    _build_design_prompt,
    _build_behavioral_prompt,
    _build_hr_prompt,
    _build_general_prompt,
    ROLE_DOMAIN_CONTEXT
)


class TestFormatCodeBlocks(unittest.TestCase):
    """Test cases for format_code_blocks function"""
    
    def test_format_code_blocks_with_python_code(self):
        """Test formatting Python code blocks"""
        input_text = "```python\ndef hello():\n    print('Hello')\n```"
        result = format_code_blocks(input_text)
        self.assertIn('```python', result)
        self.assertIn("def hello():", result)
    
    def test_format_code_blocks_with_no_code(self):
        """Test text without code blocks"""
        input_text = "This is plain text without code"
        result = format_code_blocks(input_text)
        self.assertEqual(result, input_text)
    
    def test_format_code_blocks_with_empty_input(self):
        """Test with empty or None input"""
        self.assertIsNone(format_code_blocks(None))
        self.assertEqual(format_code_blocks(""), "")
    
    def test_format_code_blocks_preserves_indentation(self):
        """Test that code block indentation is preserved"""
        input_text = "```javascript\nfunction test() {\n  return true;\n}\n```"
        result = format_code_blocks(input_text)
        self.assertIn('function test()', result)
        self.assertIn('return true;', result)


class TestPromptBuilders(unittest.TestCase):
    """Tests for newly added prompt builder helpers"""

    def test_build_technical_prompts_structure(self):
        prompts = _build_technical_prompts('Software Engineer', ROLE_DOMAIN_CONTEXT['Software Engineer'])
        self.assertIsInstance(prompts, dict)
        self.assertTrue({'code_output', 'write_program', 'theoretical'}.issubset(prompts.keys()))
        for key, message in prompts.items():
            with self.subTest(prompt=key):
                self.assertIn('Software Engineer', message)

    def test_build_analytics_prompt_includes_focus(self):
        focus = 'data storytelling'
        prompt = _build_analytics_prompt('Data Analyst', focus)
        self.assertIn('Data Analyst', prompt)
        self.assertIn(focus, prompt)

    def test_build_design_prompt_mentions_role(self):
        prompt = _build_design_prompt('Product Designer', 'holistic product thinking')
        self.assertIn('Product Designer', prompt)
        self.assertIn('holistic product thinking', prompt)

    def test_behavioral_prompt_is_question_focused(self):
        prompt = _build_behavioral_prompt('Behavioral Round')
        self.assertIn('Behavioral Round', prompt)
        self.assertIn('question', prompt.lower())

    def test_hr_prompt_mentions_alignment(self):
        prompt = _build_hr_prompt('HR Round')
        self.assertIn('HR Round', prompt)
        self.assertIn('values', prompt.lower())

    def test_general_prompt_mentions_screening(self):
        prompt = _build_general_prompt('General Interview')
        self.assertIn('General Interview', prompt)
        self.assertIn('screening', prompt.lower())


class TestAnalyzeTone(unittest.TestCase):
    """Test cases for analyze_tone function"""
    
    def test_analyze_tone_with_confident_answer(self):
        """Test tone analysis for confident answers"""
        answer = "I am very confident in my understanding of Python. It's an excellent language for data science and web development."
        result = analyze_tone(answer)
        self.assertIn('score', result)
        self.assertIn('tone', result)
        self.assertIn('feedback', result)
        self.assertIsInstance(result['score'], str)
        self.assertTrue(result['score'].endswith('%'))
    
    def test_analyze_tone_with_weak_answer(self):
        """Test tone analysis for weak/missing answers"""
        weak_answers = ["idk", "I don't know", "pata nahi", "?", "nahi"]
        for answer in weak_answers:
            result = analyze_tone(answer)
            self.assertEqual(result['tone'], "Missing or Weak")
            self.assertEqual(result['score'], "0%")
    
    def test_analyze_tone_with_short_answer(self):
        """Test tone analysis for very short answers"""
        result = analyze_tone("yes")
        self.assertEqual(result['tone'], "Missing or Weak")
    
    def test_analyze_tone_with_neutral_answer(self):
        """Test tone analysis for neutral answers"""
        answer = "Python is a programming language that is used for various applications."
        result = analyze_tone(answer)
        self.assertIn('tone', result)
        self.assertIn('feedback', result)
    
    def test_analyze_tone_with_negative_language(self):
        """Test tone analysis with negative language"""
        answer = "I'm not sure about this. It's very difficult and confusing."
        result = analyze_tone(answer)
        self.assertIn('tone', result)
        self.assertIn('feedback', result)


class TestEvaluateAnswer(unittest.TestCase):
    """Test cases for evaluate_answer function"""
    
    @patch('services.api_service.requests.post')
    def test_evaluate_answer_programming_question(self, mock_post):
        """Test evaluation of programming question answers"""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'choices': [{
                'message': {
                    'content': '{"score": 85, "tone": "Good solution", "feedback": "Well structured code", "expected_answer": "def example(): pass"}'
                }
            }]
        }
        mock_post.return_value = mock_response
        
        question = "Write a function to reverse a string"
        answer = "def reverse_string(s): return s[::-1]"
        result = evaluate_answer(question, answer)
        
        self.assertIn('score', result)
        self.assertIn('tone', result)
        self.assertIn('feedback', result)
        self.assertIn('expected_answer', result)
    
    @patch('services.api_service.requests.post')
    def test_evaluate_answer_code_output_question(self, mock_post):
        """Test evaluation of code output questions"""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'choices': [{
                'message': {
                    'content': '{"score": 90, "tone": "Correct analysis", "feedback": "You identified the output correctly", "expected_answer": "Output: 10"}'
                }
            }]
        }
        mock_post.return_value = mock_response
        
        question = "What will be the output of this code?"
        answer = "The output will be 10"
        result = evaluate_answer(question, answer)
        
        self.assertIsInstance(result, dict)
        self.assertIn('score', result)

    @patch('services.api_service.requests.post')
    def test_evaluate_answer_prompt_changes_for_programming(self, mock_post):
        """Prompt should mention code solution section for programming questions"""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'choices': [{
                'message': {
                    'content': '{"score": 80, "tone": "Solid", "feedback": "Looks good", "expected_answer": "Example"}'
                }
            }]
        }
        mock_post.return_value = mock_response

        question = "Write a function to add two numbers"
        evaluate_answer(question, "def add(a, b): return a + b")

        payload = mock_post.call_args.kwargs['json']
        prompt = payload['messages'][0]['content']
        self.assertIn("CANDIDATE'S CODE SOLUTION", prompt)
    
    @patch('services.api_service.requests.post')
    def test_evaluate_answer_api_failure(self, mock_post):
        """Test evaluation when API call fails"""
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_post.return_value = mock_response
        
        question = "What is Python?"
        answer = "Python is a programming language"
        result = evaluate_answer(question, answer)
        
        self.assertEqual(result['score'], 50)
        self.assertEqual(result['tone'], "Neutral")
    
    @patch('services.api_service.requests.post')
    def test_evaluate_answer_json_decode_error(self, mock_post):
        """Test evaluation when response is not valid JSON"""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'choices': [{
                'message': {
                    'content': 'This is not valid JSON'
                }
            }]
        }
        mock_post.return_value = mock_response
        
        question = "Explain polymorphism"
        answer = "Polymorphism allows objects to take multiple forms"
        result = evaluate_answer(question, answer)
        
        self.assertEqual(result['score'], 75)
        self.assertIn('tone', result)


class TestFetchInterviewQuestion(unittest.TestCase):
    """Test cases for fetch_interview_question function"""
    
    @patch('services.api_service.requests.post')
    def test_fetch_interview_question_technical(self, mock_post):
        """Test fetching technical interview questions"""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'choices': [{
                'message': {
                    'content': 'What is the difference between list and tuple in Python?'
                }
            }]
        }
        mock_post.return_value = mock_response
        
        result = fetch_interview_question("Technical", "Easy")
        self.assertIsNotNone(result)
        self.assertIsInstance(result, str)
        self.assertIn('?', result)
    
    @patch('services.api_service.requests.post')
    def test_fetch_interview_question_hr(self, mock_post):
        """Test fetching HR interview questions"""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'choices': [{
                'message': {
                    'content': 'Tell me about your greatest strength?'
                }
            }]
        }
        mock_post.return_value = mock_response
        
        result = fetch_interview_question("HR", "Easy")
        self.assertIsNotNone(result)
        self.assertIn('?', result)
    
    @patch('services.api_service.requests.post')
    def test_fetch_interview_question_api_error(self, mock_post):
        """Test handling of API errors"""
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_post.return_value = mock_response
        
        result = fetch_interview_question("Technical", "Easy")
        self.assertEqual(result, "Loading...")
    
    @patch('services.api_service.requests.post')
    def test_fetch_interview_question_with_code_block(self, mock_post):
        """Test fetching questions with code blocks"""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'choices': [{
                'message': {
                    'content': 'What will be the output?\n```python\nprint("Hello")\n```'
                }
            }]
        }
        mock_post.return_value = mock_response
        
        result = fetch_interview_question("Technical", "Medium")
        self.assertIsNotNone(result)
        self.assertIn('```', result)
    
    @patch('services.api_service.requests.post')
    def test_fetch_interview_question_exception(self, mock_post):
        """Test exception handling in fetch_interview_question"""
        mock_post.side_effect = Exception("Network error")
        
        result = fetch_interview_question("Technical", "Easy")
        self.assertIsNone(result)

    @patch('services.api_service.requests.post')
    def test_fetch_interview_question_invalid_role_defaults_to_general(self, mock_post):
        """Ensure unknown roles fall back to General Interview prompt"""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'choices': [{
                'message': {
                    'content': 'Describe your strengths?'
                }
            }]
        }
        mock_post.return_value = mock_response

        result = fetch_interview_question("Unknown Role", "Medium")
        self.assertEqual(result, 'Describe your strengths?')

        payload = mock_post.call_args.kwargs['json']
        system_prompt = payload['messages'][0]['content']
        self.assertIn('General Interview', system_prompt)

    @patch('services.api_service.requests.post')
    def test_fetch_interview_question_rejects_incomplete_question(self, mock_post):
        """Questions without a question mark should be rejected"""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'choices': [{
                'message': {
                    'content': 'Here is your question: This is incomplete'
                }
            }]
        }
        mock_post.return_value = mock_response

        result = fetch_interview_question("Software Engineer", "Easy")
        self.assertIsNone(result)


class TestFetchUniqueInterviewQuestions(unittest.TestCase):
    """Test cases for fetch_unique_interview_questions function"""
    
    @patch('services.api_service.fetch_interview_question')
    def test_fetch_unique_questions_success(self, mock_fetch):
        """Test successful fetching of multiple unique questions"""
        mock_fetch.side_effect = [
            "What is Python?",
            "Explain OOP?",
            "What are data types?"
        ]
        
        result = fetch_unique_interview_questions(3, "Technical", "Easy")
        self.assertEqual(len(result), 3)
        self.assertIsInstance(result, list)
    
    @patch('services.api_service.fetch_interview_question')
    def test_fetch_unique_questions_with_duplicates(self, mock_fetch):
        """Test handling of duplicate questions"""
        mock_fetch.side_effect = [
            "What is Python?",
            "What is Python?",  # Duplicate
            "Explain OOP?",
            "What are data types?"
        ]
        
        result = fetch_unique_interview_questions(3, "Technical", "Easy")
        self.assertEqual(len(result), 3)
        # Check that all questions are unique
        self.assertEqual(len(result), len(set([q.lower() for q in result])))
    
    @patch('services.api_service.fetch_interview_question')
    def test_fetch_unique_questions_with_failures(self, mock_fetch):
        """Test handling when some fetch attempts fail"""
        mock_fetch.side_effect = [
            "What is Python?",
            None,  # Failed fetch
            "Loading...",  # Invalid response
            "Explain OOP?",
        ]
        
        result = fetch_unique_interview_questions(2, "Technical", "Easy")
        self.assertEqual(len(result), 2)
    
    @patch('services.api_service.fetch_interview_question')
    def test_fetch_unique_questions_fallback(self, mock_fetch):
        """Test fallback questions when not enough unique questions are generated"""
        # Always return None to trigger fallback
        mock_fetch.return_value = None
        
        result = fetch_unique_interview_questions(2, "Technical", "Easy")
        # Fallback may return fewer than requested if dataset lacks matches; ensure list of strings
        self.assertIsInstance(result, list)
        self.assertLessEqual(len(result), 2)
        self.assertTrue(all(isinstance(q, str) for q in result))

    @patch('services.api_service.fetch_interview_question', return_value=None)
    def test_fetch_unique_questions_dataset_fallback_includes_options(self, mock_fetch):
        """Fallback should pull questions (with options) from local dataset"""
        sample_dataset = [
            {
                "role": "General Interview",
                "difficulty": "Easy",
                "question": "Sample question?",
                "options": ["Option 1", "Option 2"]
            }
        ]

        with patch('services.api_service.time.sleep', return_value=None):
            with patch('builtins.open', mock_open(read_data=json.dumps(sample_dataset))):
                with patch('services.api_service.json.load', return_value=sample_dataset):
                    result = fetch_unique_interview_questions(1, "General Interview", "Easy")

        self.assertEqual(len(result), 1)
        self.assertIn('Options:', result[0])


if __name__ == '__main__':
    unittest.main()

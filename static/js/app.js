// This code is written by - Asim Husain
class VirtualInterviewer {
    constructor() {
        this.currentSession = null;
        this.questions = [];
        this.answers = [];
        this.feedbacks = [];
        this.scores = [];
        this.tones = [];
        this.expectedAnswers = [];
        this.currentQuestionIndex = 0;
        this.isSubmitting = false;
        this.showAnswerWarning = false;
        this.recognition = null;
        this.finalTranscript = '';
        this.femaleVoice = null;
        this.difficulty = 'Easy';
        this.questionTimerId = null;
        this.questionTimeRemaining = 0;
        
        this.initializeEventListeners();
        this.hideSplashScreen();
        this.loadVoices();
    }

    loadVoices() {
        const loadVoices = () => {
            const voices = window.speechSynthesis.getVoices();
            const femaleVoice = 
                voices.find(v => v.name === "Google US English Female") ||      
                voices.find(v => v.name === "Microsoft Zira Desktop") ||       
                voices.find(v => v.name === "Samantha") ||                    
                voices.find(v => v.name.includes("Female")) ||         
                voices.find(v => v.name.includes("Zira")) ||      
                voices.find(v => v.name.includes("Karen")) ||             
                voices.find(v => v.name.includes("Tessa")) ||              
                voices.find(v => v.name.includes("Moira")) ||                  
                voices.find(v => !v.name.includes("Male") && !v.name.includes("David"));
            
            this.femaleVoice = femaleVoice || null;
        };

        if (window.speechSynthesis.getVoices().length > 0) {
            loadVoices();
        } else {
            window.speechSynthesis.onvoiceschanged = loadVoices;
        }
    }

    hideSplashScreen() {
        const splash = document.getElementById('splash-screen');
        const container = document.getElementById('app-container');
        if (splash) {
            splash.style.display = 'none';
        }
        if (container) {
            container.style.display = 'block';
        }
    }

    initializeEventListeners() {
        document.getElementById('start-btn').addEventListener('click', () => this.handleStart());
        const takeQuizButton = document.getElementById('take-quiz-btn');
        if (takeQuizButton) {
            takeQuizButton.addEventListener('click', () => this.handleTakeQuiz());
        }
        document.getElementById('submit-btn').addEventListener('click', () => this.handleSubmit());
        const backButton = document.getElementById('back-button');
        if (backButton) {
            backButton.addEventListener('click', () => this.handleBack());
        }
        document.getElementById('restart-btn').addEventListener('click', () => this.handleRestart());
        document.getElementById('mic-icon-btn').addEventListener('click', () => this.handleStartListening());
        
        document.getElementById('question-limit').addEventListener('input', (e) => {
            // Validate silently while typing; only show warning on action click
            this.validateQuestionLimit(e.target.value, false);
        });
        
        document.getElementById('answer-box').addEventListener('input', (e) => {
            if (e.target.value.trim() !== "") {
                this.showAnswerWarning = false;
                document.getElementById('answer-warning').style.display = 'none';
            }
        });
    }

    getQuestionDurationSeconds(difficulty) {
        const level = (difficulty || '').toLowerCase();
        if (level === 'medium') {
            return 90;
        }
        if (level === 'hard') {
            return 120;
        }
        return 60;
    }

    formatSecondsToClock(totalSeconds) {
        const safeSeconds = Math.max(0, Math.floor(totalSeconds || 0));
        const minutes = Math.floor(safeSeconds / 60);
        const seconds = safeSeconds % 60;
        return `${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`;
    }

    updateQuestionTimerDisplay() {
        const timerValueEl = document.getElementById('question-timer-value');
        if (timerValueEl) {
            timerValueEl.textContent = this.formatSecondsToClock(this.questionTimeRemaining);
        }
    }

    clearQuestionTimer() {
        if (this.questionTimerId) {
            clearInterval(this.questionTimerId);
            this.questionTimerId = null;
        }
    }

    startQuestionTimer(customDurationSeconds = null) {
        const nextDuration = typeof customDurationSeconds === 'number'
            ? customDurationSeconds
            : this.getQuestionDurationSeconds(this.difficulty);

        this.questionTimeRemaining = nextDuration;
        this.updateQuestionTimerDisplay();

        this.clearQuestionTimer();

        if (nextDuration <= 0) {
            return;
        }

        this.questionTimerId = setInterval(() => {
            this.questionTimeRemaining -= 1;
            if (this.questionTimeRemaining <= 0) {
                this.questionTimeRemaining = 0;
                this.updateQuestionTimerDisplay();
                this.clearQuestionTimer();
                this.handleQuestionTimeExpired();
            } else {
                this.updateQuestionTimerDisplay();
            }
        }, 1000);
    }

    handleQuestionTimeExpired() {
        if (this.isSubmitting) {
            return;
        }

        const warning = document.getElementById('answer-warning');
        if (warning) {
            warning.textContent = '⚠️ Please Answer the Question';
            warning.style.display = 'none';
        }

        this.handleSubmit({ allowEmpty: true, reason: 'timeout' });
    }

    async handleStart() {
    const role = document.getElementById('role-select').value;
        const limit = parseInt(document.getElementById('question-limit').value);
        const difficulty = document.getElementById('difficulty-select').value;
        
        if (!this.validateQuestionLimit(limit, true)) {
            return;
        }

        // Show loading state within the button
        this.showStartButtonLoading(true);

        try {
            const response = await fetch('/api/start_interview', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    role: role,
                    limit: limit,
                    difficulty: difficulty
                })
            });

            const data = await response.json();

            if (data.success) {
                this.currentSession = data.session_id;
                this.questions = data.questions;
                this.currentQuestionIndex = 0;
                this.difficulty = difficulty;
                this.questionTimeRemaining = this.getQuestionDurationSeconds(this.difficulty);
                
                this.showInterviewScreen();
                this.displayQuestion(data.questions[0], 0);
            } else {
                alert('Failed to start interview: ' + data.error);
            }
        } catch (error) {
            console.error('Error starting interview:', error);
            alert('Failed to start interview. Please try again.');
        } finally {
            // Hide loading state
            this.showStartButtonLoading(false);
        }
    }

    async handleTakeQuiz() {
        const role = document.getElementById('role-select').value;
        const numQuestions = parseInt(document.getElementById('question-limit').value, 10);
        const difficulty = document.getElementById('difficulty-select').value;

        if (!this.validateQuestionLimit(numQuestions, true)) {
            return;
        }
        // Begin 2s loading state (minimum) before quiz navigation
        this.showQuizButtonLoading(true);
        const minDelayMs = 2000; // enforce 2 second loading UX
        const startTime = performance.now();

        try {
            const params = new URLSearchParams();
            if (role) params.append('role', role);
            if (difficulty) params.append('difficulty', difficulty);
            if (!Number.isNaN(numQuestions) && numQuestions > 0) params.append('limit', numQuestions);

            const fetchFromApi = async () => {
                const query = params.toString();
                const endpoint = query ? `/api/questions?${query}` : '/api/questions';
                const response = await fetch(endpoint);
                if (!response.ok) {
                    throw new Error(`Failed to load quiz questions: ${response.status}`);
                }

                const payload = await response.json();
                if (!payload || payload.success !== true) {
                    const message = payload && payload.error ? payload.error : 'Unknown error';
                    throw new Error(message);
                }

                return {
                    questions: Array.isArray(payload.questions) ? payload.questions : [],
                    available: typeof payload.available === 'number' ? payload.available : (Array.isArray(payload.questions) ? payload.questions.length : 0)
                };
            };

            const fetchFromDataset = async () => {
                const normalizeQuestionKey = (item) => {
                    if (!item) return '';
                    const text = typeof item.question === 'string' ? item.question.trim().toLowerCase().replace(/\s+/g, ' ') : '';
                    const rolePart = typeof item.role === 'string' ? `role:${item.role.trim().toLowerCase()}` : '';
                    const diffPart = typeof item.difficulty === 'string' ? `diff:${item.difficulty.trim().toLowerCase()}` : '';
                    let optsPart = '';
                    if (Array.isArray(item.options) && item.options.length) {
                        const normalizedOptions = item.options
                            .map((opt) => (typeof opt === 'string' ? opt.trim().toLowerCase().replace(/\s+/g, ' ') : ''))
                            .filter(Boolean)
                            .sort();
                        if (normalizedOptions.length) {
                            optsPart = `opts:${normalizedOptions.join('|')}`;
                        }
                    }
                    const components = [text, optsPart, rolePart, diffPart].filter(Boolean);
                    if (!components.length && item.id !== undefined && item.id !== null) {
                        components.push(`id:${item.id}`);
                    }
                    return components.join('||');
                };

                const dedupeByQuestion = (arr) => {
                    if (!Array.isArray(arr)) return [];
                    const seen = new Set();
                    return arr.filter((item) => {
                        const key = normalizeQuestionKey(item);
                        if (!key || seen.has(key)) {
                            return false;
                        }
                        seen.add(key);
                        return true;
                    });
                };

                const responses = [`/questions.json?t=${Date.now()}`];
                let allQuestions = [];
                for (const endpoint of responses) {
                    try {
                        const resp = await fetch(endpoint, { cache: 'no-store' });
                        if (!resp.ok) continue;
                        const data = await resp.json();
                        if (Array.isArray(data)) {
                            allQuestions = data;
                            break;
                        }
                    } catch (_) {
                        // continue trying other sources
                    }
                }

                if (!Array.isArray(allQuestions) || !allQuestions.length) {
                    throw new Error('No questions data available');
                }

                const canonicalRole = typeof role === 'string' ? role.trim() : '';
                const canonicalDifficulty = typeof difficulty === 'string' ? difficulty.trim() : '';

                let filteredPool = dedupeByQuestion(allQuestions).filter((item) => {
                    const itemRole = typeof item.role === 'string' ? item.role.trim() : '';
                    const itemDifficulty = typeof item.difficulty === 'string' ? item.difficulty.trim() : '';

                    const matchesRole = (!canonicalRole || canonicalRole === 'General Interview') ? true : itemRole === canonicalRole;
                    const matchesDifficulty = canonicalDifficulty ? itemDifficulty === canonicalDifficulty : true;
                    return matchesRole && matchesDifficulty;
                });

                if (!filteredPool.length && role === 'General Interview') {
                    filteredPool = dedupeByQuestion(allQuestions);
                }

                if (!filteredPool.length) {
                    return { questions: [], available: 0 };
                }

                const pool = [...filteredPool];
                for (let i = pool.length - 1; i > 0; i--) {
                    const j = Math.floor(Math.random() * (i + 1));
                    [pool[i], pool[j]] = [pool[j], pool[i]];
                }

                const limited = (!Number.isNaN(numQuestions) && numQuestions > 0)
                    ? pool.slice(0, Math.min(numQuestions, pool.length))
                    : pool;

                return { questions: limited, available: pool.length };
            };

            let selectedQuestions = [];
            let available = 0;

            try {
                const apiResult = await fetchFromApi();
                selectedQuestions = apiResult.questions;
                available = apiResult.available;
            } catch (apiError) {
                console.warn('Quiz API request failed, falling back to local dataset.', apiError);
                const fallback = await fetchFromDataset();
                selectedQuestions = fallback.questions;
                available = fallback.available;
            }

            if (!selectedQuestions.length) {
                alert('No quiz questions found for the selected role and difficulty.');
                return;
            }

            localStorage.setItem('quizData', JSON.stringify({
                role,
                difficulty,
                requested: numQuestions,
                available,
                questions: selectedQuestions
            }));
            // Wait for minimum loading time before navigating
            const elapsedBeforeNav = performance.now() - startTime;
            if (elapsedBeforeNav < minDelayMs) {
                await new Promise(r => setTimeout(r, minDelayMs - elapsedBeforeNav));
            }
            window.location.href = '/quiz';
        } catch (error) {
            console.error('Error preparing quiz:', error);
            alert('Unable to start the quiz. Please try again.');
        } finally {
            // Ensure at least 2 seconds of loading before enabling button (in non-navigation paths)
            const elapsed = performance.now() - startTime;
            if (elapsed < minDelayMs) {
                await new Promise(r => setTimeout(r, minDelayMs - elapsed));
            }
            this.showQuizButtonLoading(false);
        }
    }

    // Function to show/hide loading state in start button
    showStartButtonLoading(show) {
        const startButton = document.getElementById('start-btn');
        
        if (show) {
            if (startButton && typeof startButton.__gooStopIntro === 'function') {
                startButton.__gooStopIntro();
            }
            // Disable button and show loading text
            startButton.disabled = true;
            startButton.innerHTML = `
                <div style="display: flex; align-items: center; justify-content: center; gap: 8px;">
                    <div class="loading-spinner"></div>
                    Starting
                </div>
            `;
            startButton.style.cursor = 'none';
        } else {
            // Re-enable button and show normal text
            startButton.disabled = false;
            startButton.innerHTML = 'Start Interview';
            startButton.style.cursor = 'none';
            if (startButton && typeof startButton.__gooRefresh === 'function') {
                requestAnimationFrame(() => {
                    if (!startButton.disabled) {
                        startButton.__gooRefresh();
                    }
                });
            }
        }
    }

    showQuizButtonLoading(show) {
        const quizButton = document.getElementById('take-quiz-btn');

        if (!quizButton) {
            return;
        }

        if (show) {
            if (typeof quizButton.__gooStopIntro === 'function') {
                quizButton.__gooStopIntro();
            }
            quizButton.disabled = true;
            quizButton.innerHTML = `
                <div style="display: flex; align-items: center; justify-content: center; gap: 8px;">
                    <div class="loading-spinner"></div>
                    Preparing
                </div>
            `;
            quizButton.style.cursor = 'none';
        } else {
            quizButton.disabled = false;
            quizButton.innerHTML = 'Take Quiz';
            quizButton.style.cursor = 'none';
            if (typeof quizButton.__gooRefresh === 'function') {
                requestAnimationFrame(() => {
                    if (!quizButton.disabled) {
                        quizButton.__gooRefresh();
                    }
                });
            }
        }
    }

    async handleSubmit(options = {}) {
        const { allowEmpty = false, reason = null } = options || {};

        if (this.isSubmitting) {
            return;
        }

        this.stopMic();
        window.speechSynthesis.cancel();

        const answerBox = document.getElementById('answer-box');
        const warning = document.getElementById('answer-warning');
        const submitButton = document.getElementById('submit-btn');

        const answer = answerBox ? answerBox.value.trim() : '';

        if (!answer && !allowEmpty) {
            this.showAnswerWarning = true;
            if (warning) {
                warning.textContent = '⚠️ Please Answer the Question';
                warning.style.display = 'block';
            }
            return;
        }

        this.showAnswerWarning = false;
        if (!allowEmpty && warning) {
            warning.textContent = '⚠️ Please Answer the Question';
            warning.style.display = 'none';
        }

        this.clearQuestionTimer();

        this.isSubmitting = true;
        if (submitButton) {
            submitButton.disabled = true;
            submitButton.innerHTML = `
                <div style="display: flex; align-items: center; justify-content: center; gap: 8px;">
                    <div class="loading-spinner"></div>
                    Analyzing
                </div>
            `;
        }

        let submissionCompleted = false;

        try {
            const response = await fetch('/api/submit_answer', {
                method: 'POST',
                credentials: 'same-origin',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    session_id: this.currentSession,
                    answer: answer
                })
            });

            const data = await response.json();

            if (data.success) {
                const recordedAnswer = answer || (reason === 'timeout' ? '(No answer - timed out)' : '');
                this.answers.push(recordedAnswer);
                this.feedbacks.push(data.feedback);
                this.scores.push(data.score);
                this.tones.push(data.tone);
                this.expectedAnswers.push(data.expected_answer);

                if (answerBox) {
                    answerBox.value = '';
                }
                this.finalTranscript = '';

                if (warning) {
                    warning.textContent = '⚠️ Please Answer the Question';
                    warning.style.display = 'none';
                }

                submissionCompleted = true;

                if (data.is_complete) {
                    this.showResults();
                } else {
                    this.currentQuestionIndex++;
                    this.displayQuestion(data.next_question, this.currentQuestionIndex);
                }
            } else {
                alert('Failed to submit answer: ' + data.error);
            }
        } catch (error) {
            console.error('Error submitting answer:', error);
            alert('Failed to submit answer. Please try again.');
        } finally {
            this.isSubmitting = false;
            if (submitButton) {
                submitButton.disabled = false;
                const isLastQuestion = this.currentQuestionIndex + 1 >= this.questions.length;
                submitButton.textContent = isLastQuestion ? 'Submit' : 'Next Question';
            }

            if (!submissionCompleted) {
                this.startQuestionTimer();
            }
        }
    }

    displayQuestion(question, index) {
        this.clearQuestionTimer();

        const warning = document.getElementById('answer-warning');
        if (warning) {
            warning.textContent = '⚠️ Please Answer the Question';
            warning.style.display = 'none';
        }

        const questionBox = document.getElementById('question-box');
        if (!questionBox) {
            return;
        }
        const duration = this.getQuestionDurationSeconds(this.difficulty);
        this.questionTimeRemaining = duration;
        const timerDisplay = this.formatSecondsToClock(this.questionTimeRemaining);

        questionBox.innerHTML = `
            <div class="question-timer" id="question-timer" aria-live="polite">
                <span class="timer-value" id="question-timer-value">${timerDisplay}</span>
            </div>
            <p style="display: flex; align-items: center; gap: 8px; margin-bottom: 12px;">
                <strong>Question ${index + 1}:</strong>
                <img src="/static/assets/icons/speaker.png" alt="Speak" 
                     onclick="virtualInterviewer.speakQuestion('${this.escapeHtml(question)}')"
                     style="width: 30px; height: 30px; cursor: pointer;" 
                     title="Click to listen">
            </p>
            <div>${this.formatQuestionWithCode(question)}</div>
        `;

        const submitButton = document.getElementById('submit-btn');
        if (submitButton) {
            const isLastQuestion = index + 1 >= this.questions.length;
            submitButton.textContent = isLastQuestion ? 'Submit' : 'Next Question';
            submitButton.disabled = false;
        }

        this.startQuestionTimer(duration);
    }

    speakQuestion(question) {
        const synth = window.speechSynthesis;

        if (synth.speaking) {
            synth.cancel();
            return;
        }

        const utterance = new SpeechSynthesisUtterance(question);
        utterance.lang = "en-US";
        utterance.rate = 1;
        
        // Use female voice if available
        if (this.femaleVoice) {
            utterance.voice = this.femaleVoice;
        }

        synth.speak(utterance);
    }

    handleStartListening() {
        this.stopMic(); 
        
        if ('webkitSpeechRecognition' in window) {
            this.recognition = new webkitSpeechRecognition();
            this.recognition.lang = 'en-US';
            this.recognition.continuous = true;
            this.recognition.interimResults = true;

            this.finalTranscript = '';

            this.recognition.onresult = (event) => {
                let interimTranscript = '';

                for (let i = event.resultIndex; i < event.results.length; ++i) {
                    const transcript = event.results[i][0].transcript;
                    if (event.results[i].isFinal) {
                        this.finalTranscript += transcript + ' ';
                    } else {
                        interimTranscript += transcript;
                    }
                }

                document.getElementById('answer-box').value = this.finalTranscript + interimTranscript;
            };

            this.recognition.onerror = (e) => {
                alert('Mic Error: ' + e.error);
            };

            this.recognition.start();
        } else {
            alert('Speech recognition not supported in this browser.');
        }
    }

    stopMic() {
        if (this.recognition) {
            this.recognition.stop();
            this.recognition = null;
        }
    }

    showResults() {
        this.clearQuestionTimer();

        let resultsHTML = '';
        
        this.questions.forEach((question, index) => {
            resultsHTML += `
                <div class="feedback-box">
                    <div class="feedback-question-row">
                        <strong>Q${index + 1}:</strong>
                        <div class="feedback-question-text">${this.formatQuestionWithCode(question)}</div>
                    </div>

                    <p style="margin-bottom: 5px;">
                        <strong>Expected Answer:</strong> ${this.formatAnswerWithCode(this.expectedAnswers[index] || 'N/A')}
                    </p>

                    <p><strong>Your Answer:</strong> ${this.escapeHtml(this.answers[index])}</p>
                    <p><strong>Feedback:</strong> ${this.escapeHtml(this.feedbacks[index])}</p>
                    <p><strong>Accuracy:</strong> ${this.scores[index]}%</p>
                    <p><strong>Tone:</strong> ${this.tones[index]}</p>
                    <hr>
                </div>
            `;
        });

        document.getElementById('results-content').innerHTML = resultsHTML;
        
        const overallScore = this.calculateAverageScore();
        document.getElementById('overall-score').textContent = overallScore;
        document.getElementById('overall-result').style.display = 'block';
        
        document.getElementById('interview-screen').style.display = 'none';
        document.getElementById('results-section').style.display = 'block';
        document.body.classList.remove('interview-mode');
        document.body.classList.add('feedback-mode');
        window.scrollTo({ top: 0, left: 0, behavior: 'auto' });

    }

    calculateAverageScore() {
        if (this.scores.length === 0) return 0;
        const total = this.scores.reduce((sum, score) => {
            const numScore = typeof score === 'number' ? score : parseInt(score);
            return sum + (isNaN(numScore) ? 0 : numScore);
        }, 0);
        return Math.round(total / this.scores.length);
    }

    showInterviewScreen() {
        document.getElementById('landing-card').style.display = 'none';
        document.getElementById('interview-screen').style.display = 'block';
        document.getElementById('results-section').style.display = 'none';
        document.body.classList.add('interview-mode');
        document.body.classList.remove('feedback-mode');
        window.scrollTo({ top: 0, left: 0, behavior: 'auto' });

    }

    handleBack() {
        this.stopMic();
        window.speechSynthesis.cancel(); 
        
        if (this.currentSession) {
            fetch(`/api/end_session/${this.currentSession}`, { method: 'DELETE' });
        }
        this.resetInterview();
        document.getElementById('interview-screen').style.display = 'none';
        document.getElementById('landing-card').style.display = 'flex';
        document.body.classList.remove('interview-mode', 'feedback-mode');
        window.scrollTo({ top: 0, left: 0, behavior: 'auto' });

        const startButton = document.getElementById('start-btn');
        if (startButton && typeof startButton.__gooRefresh === 'function') {
            requestAnimationFrame(() => {
                if (!startButton.disabled) {
                    startButton.__gooRefresh();
                }
            });
        }
    }

    handleRestart() {
        this.stopMic();
        window.speechSynthesis.cancel(); 
        
        this.resetInterview();
        document.getElementById('results-section').style.display = 'none';
        document.getElementById('landing-card').style.display = 'flex';
        document.body.classList.remove('interview-mode', 'feedback-mode');
        window.scrollTo({ top: 0, left: 0, behavior: 'auto' });

        const startButton = document.getElementById('start-btn');
        if (startButton && typeof startButton.__gooRefresh === 'function') {
            requestAnimationFrame(() => {
                if (!startButton.disabled) {
                    startButton.__gooRefresh();
                }
            });
        }
    }

    resetInterview() {
        this.currentSession = null;
        this.questions = [];
        this.answers = [];
        this.feedbacks = [];
        this.scores = [];
        this.tones = [];
        this.expectedAnswers = [];
        this.currentQuestionIndex = 0;
        this.isSubmitting = false;
        this.showAnswerWarning = false;
        document.getElementById('answer-box').value = '';
        this.finalTranscript = '';
        this.stopMic();
        window.speechSynthesis.cancel();
        this.clearQuestionTimer();
        this.questionTimeRemaining = 0;
        this.updateQuestionTimerDisplay();
    }

    validateQuestionLimit(value, show = true) {
        const warning = document.getElementById('limit-warning');
        const numValue = parseInt(value);
        const invalid = (!value || isNaN(numValue) || numValue < 1 || numValue > 100);

        if (show) {
            warning.style.display = invalid ? 'block' : 'none';
        } else {
            // While typing, do not show the warning; but clear it if value becomes valid
            if (!invalid) warning.style.display = 'none';
        }
        return !invalid;
    }

    formatQuestionWithCode(question) {
        if (!question) return '';
        
        let formatted = question.replace(/```(\w+)?\n([\s\S]*?)```/g, (match, language, code) => {
            const cleanCode = code.replace(/^\n+|\n+$/g, ''); 
            const escapedCode = this.escapeHtml(cleanCode);
            
            return `
                <div class="code-container">
                    <pre><code>${escapedCode}</code></pre>
                </div>
            `;
        });

        // Convert line breaks and basic markdown
        formatted = formatted.replace(/\n/g, '<br>');
        formatted = formatted.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
        formatted = formatted.replace(/\*(.*?)\*/g, '<em>$1</em>');
        
        return formatted;
    }

    formatAnswerWithCode(answer) {
        if (!answer) return 'N/A';
        
        // Check if answer contains code blocks
        if (answer.includes('```')) {
            return answer.replace(/```(\w+)?\n([\s\S]*?)```/g, (match, language, code) => {
                const cleanCode = code.replace(/^\n+|\n+$/g, '');
                const escapedCode = this.escapeHtml(cleanCode);
                
                return `
                    <div class="code-container">
                        <pre><code>${escapedCode}</code></pre>
                    </div>
                `;
            });
        }

        const codePatterns = [
            /def\s+\w+\(/, /function\s+\w+\(/, /class\s+\w+/, /import\s+\w+/, 
            /console\.log\(/, /print\(/, /public\s+class/, /#include\s*</,
            /void\s+\w+\(/, /int\s+\w+\(/, /String\s+\w+/, /System\.out\.print/,
            /printf\(/, /cout\s*<</, /scanf\(/, /cin\s*>>/, /return\s+\w+/,
            /if\s*\(.*\)/, /for\s*\(.*\)/, /while\s*\(.*\)/, /switch\s*\(.*\)/,
            /try\s*{/, /catch\s*\(.*\)/, /\.\w+\(.*\)/, /=\s*[\w\[]/, /<\w+>/, /@\w+/
        ];
        
        const looksLikeCode = codePatterns.some(pattern => pattern.test(answer));
        
        if (looksLikeCode) {
            return `
                <div class="code-container">
                    <pre><code>${this.escapeHtml(answer)}</code></pre>
                </div>
            `;
        }
        
        return this.escapeHtml(answer).replace(/\n/g, '<br>');
    }

    escapeHtml(text) {
        if (!text) return '';
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
}

const applyStoredTheme = () => {
    if (window.ivTheme && typeof window.ivTheme.refresh === 'function') {
        window.ivTheme.refresh();
        return;
    }

    const prefersDark = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches;
    const storedTheme = localStorage.getItem('iv_theme');
    const theme = storedTheme || (prefersDark ? 'theme-dark' : 'theme-light');
    document.body.classList.remove('theme-light', 'theme-dark');
    document.body.classList.add(theme);
};

// Initialize the application when the page loads
let virtualInterviewer;
document.addEventListener('DOMContentLoaded', () => {
        applyStoredTheme();
        const isStartPage = document.body.classList.contains('start-page');
        if (!isStartPage) {
                virtualInterviewer = new VirtualInterviewer();
        }

    const streakCountEl = document.getElementById('streakCount');
    const streakDaysEl = document.getElementById('streakDays');
    const streakLabelEl = document.getElementById('streakLabel');
    if (streakCountEl && streakDaysEl && streakLabelEl) {
        const configs = [
            { label: 'Focus score', count: 78, activeDays: 5 },
            { label: 'Consistency tracker', count: 6, activeDays: 6 },
            { label: 'Session momentum', count: 4, activeDays: 4 },
            { label: 'Practice pulse', count: 92, activeDays: 5 },
            { label: 'Readiness meter', count: 81, activeDays: 4 },
            { label: 'Skill cadence', count: 3, activeDays: 3 },
            { label: 'Interview momentum', count: 7, activeDays: 5 }
        ];

        const applyConfig = (config) => {
            streakLabelEl.textContent = config.label;
            streakCountEl.textContent = String(config.count);
            Array.from(streakDaysEl.children).forEach((el, idx) => {
                if (idx < config.activeDays) {
                    el.classList.add('is-active');
                } else {
                    el.classList.remove('is-active');
                }
            });
        };

        let labelIndex = 0;
        applyConfig(configs[labelIndex]);
        setInterval(() => {
            labelIndex = (labelIndex + 1) % configs.length;
            applyConfig(configs[labelIndex]);
        }, 5000);
    }

        const donutCtx = document.getElementById('landingDonut');
        const donutLegend = document.getElementById('landingDonutLegend');
        if (donutCtx && window.Chart) {
            const styles = getComputedStyle(document.body);
            const chart1 = styles.getPropertyValue('--chart-1').trim() || '#58a6ff';
            const chart2 = styles.getPropertyValue('--chart-2').trim() || '#2ea043';
            const donutChart = new Chart(donutCtx, {
                type: 'doughnut',
                data: {
                    labels: ['Quiz', 'Interview'],
                    datasets: [{
                        data: [0, 0],
                        backgroundColor: [chart1, chart2],
                        hoverOffset: 10,
                        spacing: 3,
                        borderWidth: 0
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    cutout: '68%',
                    animation: { animateRotate: true, animateScale: true, duration: 1200, easing: 'easeOutQuart' },
                    layout: { padding: 6 },
                    elements: { arc: { borderRadius: 6 } },
                    plugins: { legend: { display: false }, tooltip: { enabled: false } }
                }
            });

            const renderLegend = (values) => {
                if (!donutLegend) return;
                donutLegend.innerHTML = values
                    .map((val, idx) => {
                        const label = donutChart.data.labels[idx];
                        const color = donutChart.data.datasets[0].backgroundColor[idx];
                        return `<div class="legend-item"><span class="swatch" style="background:${color}"></span><span class="label">${label}</span><span class="value">${val}</span></div>`;
                    })
                    .join('');
            };

            fetch('/api/results')
                .then((resp) => resp.ok ? resp.json() : Promise.reject(resp))
                .then((data) => {
                    if (!data || !data.success || !Array.isArray(data.results)) {
                        return;
                    }
                    const counts = data.results.reduce((acc, row) => {
                        const kind = (row.type || '').toString().toLowerCase();
                        if (kind === 'quiz') acc.quiz += 1;
                        else acc.interview += 1;
                        return acc;
                    }, { quiz: 0, interview: 0 });
                    donutChart.data.datasets[0].data = [counts.quiz, counts.interview];
                    donutChart.update();
                    renderLegend([counts.quiz, counts.interview]);
                })
                .catch(() => {
                    renderLegend([0, 0]);
                });
        }

        if (typeof window.ivRefreshGooButtons === 'function') {
                window.ivRefreshGooButtons();
        }
});

// Start page heading animation (merged from heading-anim.js)
document.addEventListener('DOMContentLoaded',()=>{
    const body=document.body;
    if(!body.classList.contains('heading-anim-init')) return; // only on start page when init class is present
    const left=document.querySelector('.start-heading-left');
    const right=document.querySelector('.start-heading-right');
    const bar=document.querySelector('.start-heading-bar');
    const subheading=document.querySelector('.start-subheading');
    const cta=document.querySelector('.start-cta');
    const revealSubheading=()=>{
        if(subheading){
            subheading.classList.add('is-visible');
        }
        if(cta){
            cta.classList.add('is-visible');
        }
    };
    if(!left||!right||!bar) { body.classList.remove('heading-anim-init'); revealSubheading(); return; }

    const prefersReduced = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    if(prefersReduced){
        // Immediately reveal, skip animation
        left.style.opacity='1'; left.style.transform='none';
        right.style.opacity='1'; right.style.transform='none';
        body.classList.remove('heading-anim-init');
        revealSubheading();
        return;
    }

    // Force reflow for initial states
    left.offsetWidth; right.offsetWidth; bar.offsetWidth;

    // Sequence: fade in separator line after 1000ms, then start word reveal after line fully visible
    setTimeout(()=>{
        bar.style.opacity='1';
        // After line fade completes (~700ms), start BOT then INTERV
        setTimeout(()=>{
            right.style.transition='clip-path 1000ms cubic-bezier(.4,0,.2,1)';
            right.style.clipPath='inset(0 0 0 0)';
            right.addEventListener('transitionend', function handler(e){
                if(e.propertyName!=='clip-path') return;
                right.removeEventListener('transitionend', handler);
                setTimeout(()=>{
                    left.style.transition='clip-path 1000ms cubic-bezier(.4,0,.2,1)';
                    left.style.clipPath='inset(0 0 0 0)';
                    left.addEventListener('transitionend', function endLeft(ev){
                        if(ev.propertyName!=='clip-path') return;
                        left.removeEventListener('transitionend', endLeft);
                        body.classList.remove('heading-anim-init');
                        revealSubheading();
                    });
                },150);
            });
        },750); // delay matches bar fade duration for clean staging
    },1000);
});

if (typeof module !== 'undefined' && module.exports) {
    module.exports = { VirtualInterviewer, applyStoredTheme };
}
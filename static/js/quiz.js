// Quiz page logic - prepares questions, handles submission, and reports score.
;(function () {
  let quizState = null
  let currentQuestionIndex = 0
  const answersSelected = []
  let isLocked = false
  let quizStartedAt = null
  let questionTimerId = null
  let questionTimeRemaining = 0
  let onTimerExpired = null
  let submitButtonEl = null
  let retakeButtonEl = null
  let resultContainerEl = null
  let timerContainerEl = null

  const getQuestionDurationSeconds = (difficulty) => {
    const level = (typeof difficulty === 'string' ? difficulty : '').toLowerCase()
    if (level === 'medium') return 90
    if (level === 'hard') return 120
    return 60
  }

  const formatSecondsToClock = (totalSeconds) => {
    const safe = Math.max(0, Math.floor(totalSeconds || 0))
    const minutes = Math.floor(safe / 60)
    const seconds = safe % 60
    return `${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`
  }

  const updateQuizTimerDisplay = () => {
    const timerValueEl = document.getElementById('quiz-timer-value')
    if (timerValueEl) {
      timerValueEl.textContent = formatSecondsToClock(questionTimeRemaining)
    }
  }

  const clearQuizTimer = () => {
    if (questionTimerId) {
      clearInterval(questionTimerId)
      questionTimerId = null
    }
    onTimerExpired = null
  }

  const startQuizTimer = (durationSeconds, timeoutCallback) => {
    clearQuizTimer()

    questionTimeRemaining = typeof durationSeconds === 'number'
      ? durationSeconds
      : getQuestionDurationSeconds(quizState?.difficulty)

    updateQuizTimerDisplay()

    onTimerExpired = typeof timeoutCallback === 'function' ? timeoutCallback : null

    if (questionTimeRemaining <= 0) {
      const callback = onTimerExpired
      clearQuizTimer()
      if (typeof callback === 'function') {
        callback()
      }
      return
    }

    questionTimerId = setInterval(() => {
      questionTimeRemaining -= 1
      if (questionTimeRemaining <= 0) {
        questionTimeRemaining = 0
        updateQuizTimerDisplay()
        const callback = onTimerExpired
        clearQuizTimer()
        if (typeof callback === 'function') {
          callback()
        }
      } else {
        updateQuizTimerDisplay()
      }
    }, 1000)
  }

  const escapeHtml = (value) => {
    if (value === null || value === undefined) {
      return ''
    }
    return String(value)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;')
  }

  const buildQuestionCard = (question, index) => {
    const article = document.createElement('article')
    article.className = 'quiz-card'

    const questionNumber = index + 1
    const optionsMarkup = (Array.isArray(question.options) ? question.options : []).map((option, optionIndex) => {
      const optionId = `question-${index}-option-${optionIndex}`
      return `
        <div class="quiz-option">
          <input type="checkbox" id="${optionId}" name="question-${index}" value="${escapeHtml(option)}" data-question-index="${index}">
          <span>${escapeHtml(option)}</span>
        </div>
      `
    }).join('')

    article.innerHTML = `
      <h2 class="quiz-question">Q${questionNumber}. ${escapeHtml(question.question)}</h2>
      <div class="quiz-options">
        ${optionsMarkup}
      </div>
    `

    return article
  }

  const attachExclusiveSelection = (root) => {
    const checkboxes = root.querySelectorAll('.quiz-option input[type="checkbox"]')
    checkboxes.forEach((checkbox) => {
      checkbox.addEventListener('change', (event) => {
        if (!event.target.checked) return
        const targetName = event.target.getAttribute('name')
        root.querySelectorAll(`input[name="${targetName}"]`).forEach((peer) => {
          if (peer !== event.target) peer.checked = false
        })

        // Persist selection for current question
        try {
          const name = event.target.getAttribute('name') || ''
          const idx = parseInt(name.split('-')[1], 10)
          if (!Number.isNaN(idx)) {
            answersSelected[idx] = event.target.value
          }
        } catch (_) {}
      })
    })

    // Allow clicking the whole row to toggle the checkbox
    root.querySelectorAll('.quiz-option').forEach((row) => {
      row.addEventListener('click', (e) => {
        if (e.target && e.target.tagName === 'INPUT') return
        const input = row.querySelector('input[type="checkbox"]')
        if (!input) return
        input.checked = !input.checked
        input.dispatchEvent(new Event('change', { bubbles: true }))
      })
    })
  }

  const renderQuiz = () => {
    const rawData = localStorage.getItem('quizData')

    if (!rawData) {
      window.location.href = '/landing'
      return
    }

    try {
      quizState = JSON.parse(rawData)
    } catch (error) {
      console.error('Failed to parse saved quiz data:', error)
      window.location.href = '/landing'
      return
    }

    const {
      role = 'General',
      difficulty = '',
      questions = []
    } = quizState || {}

    if (timerContainerEl) {
      timerContainerEl.style.display = ''
    }

    const label = document.getElementById('quiz-label')
    const meta = document.getElementById('quiz-meta')
    const questionsContainer = document.getElementById('quiz-questions')
    const prevBtn = document.getElementById('prev-question-btn')
    const nextBtn = document.getElementById('next-question-btn')
    const submitButton = submitButtonEl

    if (!label || !meta || !questionsContainer || !submitButton || !prevBtn || !nextBtn) {
      console.warn('Quiz layout is missing required elements.')
      return
    }

    label.textContent = `${role} Assessment`

    const metaParts = []
    if (difficulty) {
      metaParts.push(`Difficulty: ${difficulty}`)
    }
    if (typeof quizState?.requested === 'number' && typeof quizState?.available === 'number' && quizState.available < quizState.requested) {
      metaParts.push(`Showing ${questions.length} of ${quizState.requested} requested`)
    }
    metaParts.push(`Questions: ${questions.length}`)
    meta.textContent = metaParts.join(' • ')

    if (!questions.length) {
      questionsContainer.innerHTML = '<p class="quiz-empty">No quiz questions were found. Please return and try a different selection.</p>'
      submitButton.disabled = true
      prevBtn.style.display = 'none'
      nextBtn.style.display = 'none'
      questionTimeRemaining = 0
      updateQuizTimerDisplay()
      clearQuizTimer()
      return
    }

    const handleTimeout = () => {
      if (isLocked) return
      if (currentQuestionIndex < questions.length - 1) {
        currentQuestionIndex += 1
        renderCurrent()
      } else {
        completeQuizSubmission({ reason: 'timeout' })
      }
    }

    const startCurrentQuestionTimer = () => {
      if (isLocked) {
        clearQuizTimer()
        return
      }
      startQuizTimer(getQuestionDurationSeconds(difficulty), handleTimeout)
    }

    const renderCurrent = () => {
      clearQuizTimer()

      const question = questions[currentQuestionIndex]
      const optionsMarkup = (Array.isArray(question.options) ? question.options : []).map((option, optionIndex) => {
        const optionId = `question-${currentQuestionIndex}-option-${optionIndex}`
        const checked = answersSelected[currentQuestionIndex] === option ? 'checked' : ''
        return `
          <div class="quiz-option">
            <input type="checkbox" id="${optionId}" name="question-${currentQuestionIndex}" value="${escapeHtml(option)}" ${checked}>
            <span>${escapeHtml(option)}</span>
          </div>
        `
      }).join('')

      const markup = `
        <h2 class="quiz-question">Q${currentQuestionIndex + 1}. ${escapeHtml(question.question)}</h2>
        <div class="quiz-options">${optionsMarkup}</div>
      `

      questionsContainer.innerHTML = markup
      attachExclusiveSelection(questionsContainer)

      if (isLocked) {
        questionsContainer.querySelectorAll('input[type="checkbox"]').forEach((el) => {
          el.disabled = true
        })
      }

      prevBtn.style.visibility = currentQuestionIndex === 0 ? 'hidden' : 'visible'
      nextBtn.style.visibility = currentQuestionIndex === questions.length - 1 ? 'hidden' : 'visible'
      submitButton.style.display = currentQuestionIndex === questions.length - 1 ? 'inline-flex' : 'none'
      if (typeof submitButton.__gooRefresh === 'function') submitButton.__gooRefresh()
      if (typeof prevBtn.__gooRefresh === 'function') prevBtn.__gooRefresh()
      if (typeof nextBtn.__gooRefresh === 'function') nextBtn.__gooRefresh()

      startCurrentQuestionTimer()
    }

    const goPrev = () => {
      if (isLocked) return
      if (currentQuestionIndex > 0) {
        currentQuestionIndex -= 1
        renderCurrent()
      }
    }

    const goNext = () => {
      if (isLocked) return
      if (currentQuestionIndex < questions.length - 1) {
        currentQuestionIndex += 1
        renderCurrent()
      }
    }

    prevBtn.addEventListener('click', goPrev)
    nextBtn.addEventListener('click', goNext)
    prevBtn.addEventListener('keydown', (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); goPrev() } })
    nextBtn.addEventListener('keydown', (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); goNext() } })

    renderCurrent()
    quizStartedAt = Date.now()
  }

  const calculateScore = () => {
    if (!quizState || !Array.isArray(quizState.questions)) {
      return { score: 0, total: 0 }
    }

    let score = 0

    quizState.questions.forEach((question, index) => {
      if (answersSelected[index] && answersSelected[index] === question.correct_answer) {
        score += 1
      }
    })

    return { score, total: quizState.questions.length }
  }

  const showConfirm = (onContinue) => {
    const overlay = document.createElement('div')
    overlay.className = 'confirm-overlay'
    overlay.innerHTML = `
      <div class="confirm-modal" role="dialog" aria-modal="true" aria-labelledby="confirm-title">
        <h3 id="confirm-title" class="confirm-title">Submit Quiz</h3>
        <p class="confirm-text">Not Allowed to Modify the Answers. Are You Sure</p>
        <div class="confirm-actions">
          <button type="button" class="goo-button" data-goo-magnet="off" id="confirm-cancel">Cancel</button>
          <button type="button" class="goo-button" data-goo-magnet="off" id="confirm-continue">Continue</button>
        </div>
      </div>
    `
    document.body.appendChild(overlay)
    if (window.ivRefreshGooButtons) {
      window.ivRefreshGooButtons(overlay)
    }
    const cancelBtn = overlay.querySelector('#confirm-cancel')
    const contBtn = overlay.querySelector('#confirm-continue')
    cancelBtn.addEventListener('click', () => overlay.remove())
    contBtn.addEventListener('click', () => {
      overlay.remove()
      if (typeof onContinue === 'function') onContinue()
    })
  }

  const lockQuiz = () => {
    if (isLocked) return
    isLocked = true
    clearQuizTimer()
    questionTimeRemaining = 0
    updateQuizTimerDisplay()
    if (timerContainerEl) {
      timerContainerEl.style.display = 'none'
    }
    const shell = document.querySelector('.quiz-shell')
    if (shell) shell.classList.add('quiz-locked')
    document.querySelectorAll('#quiz-questions input[type="checkbox"]').forEach((el) => {
      el.disabled = true
    })
  }

  const completeQuizSubmission = ({ reason = 'manual' } = {}) => {
    if (isLocked) return

    if (submitButtonEl && typeof submitButtonEl.__gooStopIntro === 'function') {
      submitButtonEl.__gooStopIntro()
    }

    lockQuiz()

    const { score, total } = calculateScore()

    if (resultContainerEl) {
      resultContainerEl.classList.add('is-visible')
    }

    renderRichResult({ score, total })

    if (reason === 'timeout' && resultContainerEl && !resultContainerEl.querySelector('.quiz-timeout-note')) {
      const note = document.createElement('p')
      note.className = 'quiz-timeout-note'
      note.textContent = '⏰ Quiz submitted automatically because time expired.'
      resultContainerEl.insertAdjacentElement('afterbegin', note)
    }

    try {
      if (window.IS_AUTHENTICATED) {
        const elapsedSeconds = quizStartedAt ? Math.max(0, Math.round((Date.now() - quizStartedAt) / 1000)) : null
        fetch('/api/save_quiz_result', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            role: quizState?.role || 'Quiz',
            difficulty: quizState?.difficulty || '',
            score,
            total,
            selections: answersSelected,
            questions: (quizState?.questions || []).map(q => ({
              question: q.question,
              correct_answer: q.correct_answer,
              options: q.options
            })),
            duration_seconds: elapsedSeconds
          })
        }).then(r => r.json()).then(resp => {
          if (!resp.success) {
            console.warn('Quiz result save failed:', resp.error)
          }
        }).catch(err => console.warn('Quiz save error', err))
      }
    } catch (e) {
      console.warn('Quiz save threw', e)
    }

    const qWrap = document.getElementById('quiz-questions')
    if (qWrap) qWrap.style.display = 'none'
    const nav = document.querySelector('.quiz-nav')
    if (nav) nav.style.display = 'none'

    if (submitButtonEl) {
      submitButtonEl.disabled = true
      submitButtonEl.style.display = 'none'
    }

    if (retakeButtonEl) {
      retakeButtonEl.style.display = 'inline-flex'
      if (typeof retakeButtonEl.__gooRefresh === 'function') retakeButtonEl.__gooRefresh()
    }
  }

  const renderRichResult = ({ score, total }) => {
    const wrong = Math.max(0, total - score)
    const percent = total > 0 ? Math.round((score / total) * 100) : 0
    const resultContainer = document.getElementById('quiz-result')
    if (!resultContainer) return
    resultContainer.classList.add('quiz-result-rich')
    resultContainer.innerHTML = `
      <div class="result-wrap">
        <div class="result-pie" id="result-pie" style="--p:0">
          <span class="result-percent-badge" id="result-percent">0%</span>
        </div>
        <div class="result-stats">
          <div class="stat-card">
            <span class="stat-label stat-total">Total Questions</span>
            <span class="stat-value">${total}</span>
          </div>
          <div class="stat-card">
            <span class="stat-label stat-ok">Correct Answers</span>
            <span class="stat-value">${score}</span>
          </div>
          <div class="stat-card">
            <span class="stat-label stat-bad">Wrong Answers</span>
            <span class="stat-value">${wrong}</span>
          </div>
        </div>
      </div>
    `
    // Animate donut and number
    const pie = document.getElementById('result-pie')
    const number = document.getElementById('result-percent')
    let start = null
    const duration = 900
    const animate = (ts) => {
      if (!start) start = ts
      const t = Math.min(1, (ts - start) / duration)
      const val = Math.round(percent * t)
      pie.style.setProperty('--p', val)
      number.textContent = `${val}%`
      if (t < 1) requestAnimationFrame(animate)
    }
    requestAnimationFrame(animate)
    // attach download button (ensure single instance)
    try {
      // remove existing if present
      const existing = resultContainer.querySelector('#downloadResultBtn')
      if (existing) existing.remove()
      const btn = document.createElement('button')
      btn.id = 'downloadResultBtn'
      btn.className = 'result-download-btn'
      btn.title = 'Download Result'
      btn.setAttribute('aria-label', 'Download Result')
  btn.innerHTML = `<svg width="36" height="36" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 14 14" aria-hidden="true"><g fill="none" fill-rule="evenodd" clip-rule="evenodd"><path fill="#8fbffa" d="M.999 9.448a1 1 0 0 1 1 1v.834c0 .142.062.302.211.437c.153.138.38.23.635.23h8.31a.95.95 0 0 0 .635-.23a.6.6 0 0 0 .21-.437v-.834a1 1 0 1 1 2 0v.834a2.6 2.6 0 0 1-.87 1.921a2.95 2.95 0 0 1-1.976.746H2.846a2.95 2.95 0 0 1-1.975-.746A2.6 2.6 0 0 1 0 11.282v-.834a1 1 0 0 1 1-1Z"/><path fill="#2859c5" d="M3.37 6.589a1.28 1.28 0 0 1 .419-1.485c.383-.292.89-.35 1.328-.181c.245.094.552.197.883.274V1a1 1 0 1 1 2 0v4.197c.331-.078.638-.18.883-.274a1.38 1.38 0 0 1 1.329.181c.425.324.639.907.418 1.485c-.257.674-.763 1.294-1.33 1.774c-.571.485-1.287.897-2.048 1.087a1.04 1.04 0 0 1-.504 0c-.76-.19-1.477-.602-2.049-1.087c-.566-.48-1.072-1.1-1.33-1.774Z"/></g></svg>`
      const isMobile = window.matchMedia('(max-width: 640px)').matches
      const pieTarget = document.getElementById('result-pie')
      const targetForDownload = (isMobile && pieTarget) ? pieTarget : resultContainer
      targetForDownload.appendChild(btn)

      // Summary button: shows full question/answer breakdown
      const existingSummary = resultContainer.querySelector('#showSummaryBtn')
      if (existingSummary) existingSummary.remove()
      const summaryBtn = document.createElement('button')
      summaryBtn.id = 'showSummaryBtn'
      summaryBtn.className = 'result-summary-btn'
  summaryBtn.type = 'button'
  // use provided summary SVG as the button content (keeps accessible label)
  // make SVG theme-aware by using currentColor for fills
  summaryBtn.innerHTML = `<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 36 36" aria-hidden="true"><path fill="currentColor" d="M32 6H4a2 2 0 0 0-2 2v20a2 2 0 0 0 2 2h28a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2Zm0 22H4V8h28Z" class="clr-i-outline clr-i-outline-path-1"/><path fill="currentColor" d="M9 14h18a1 1 0 0 0 0-2H9a1 1 0 0 0 0 2Z" class="clr-i-outline clr-i-outline-path-2"/><path fill="currentColor" d="M9 18h18a1 1 0 0 0 0-2H9a1 1 0 0 0 0 2Z" class="clr-i-outline clr-i-outline-path-3"/><path fill="currentColor" d="M9 22h10a1 1 0 0 0 0-2H9a1 1 0 0 0 0 2Z" class="clr-i-outline clr-i-outline-path-4"/><path fill="none" d="M0 0h36v36H0z"/></svg>`
  summaryBtn.title = 'Show full summary of questions'
      const targetForSummary = (isMobile && pieTarget) ? pieTarget : resultContainer
      targetForSummary.appendChild(summaryBtn)

      summaryBtn.addEventListener('click', () => {
        try {
          const overlay = document.createElement('div')
          overlay.className = 'summary-overlay'
          const modal = document.createElement('div')
          modal.className = 'summary-modal'
          modal.setAttribute('role', 'dialog')
          modal.setAttribute('aria-modal', 'true')
          modal.innerHTML = `
            <div class="summary-header">
              <h3>Quiz Summary</h3>
              <button class="summary-close" aria-label="Close summary">×</button>
            </div>
            <div class="summary-body"></div>
          `
          overlay.appendChild(modal)
          document.body.appendChild(overlay)

          const body = modal.querySelector('.summary-body')
          // Build questions list
          const qList = document.createElement('ol')
          qList.className = 'summary-questions'
          const questions = quizState?.questions || []
          questions.forEach((q, qi) => {
            const li = document.createElement('li')
            li.className = 'summary-question'
            const qTitle = document.createElement('div')
            qTitle.className = 'summary-qtitle'
            qTitle.textContent = `Q${qi + 1}. ${q.question}`
            li.appendChild(qTitle)

            const opts = document.createElement('ul')
            opts.className = 'summary-options'
            const userChoice = answersSelected[qi]
            const correct = q.correct_answer
            ;(Array.isArray(q.options) ? q.options : []).forEach((opt) => {
              const optLi = document.createElement('li')
              optLi.className = 'summary-option'
              // markers
              if (opt === correct) optLi.classList.add('correct')
              if (userChoice && opt === userChoice) optLi.classList.add('chosen')
              // show content
              const span = document.createElement('span')
              span.textContent = opt
              optLi.appendChild(span)
              // add label for clarity
              if (opt === correct) {
                const badge = document.createElement('small')
                badge.className = 'option-badge option-correct'
                badge.textContent = 'Correct'
                optLi.appendChild(badge)
              }
              if (userChoice && opt === userChoice && opt !== correct) {
                const badge = document.createElement('small')
                badge.className = 'option-badge option-wrong'
                badge.textContent = 'Your answer'
                optLi.appendChild(badge)
              }
              if (userChoice && opt === userChoice && opt === correct) {
                const badge = document.createElement('small')
                badge.className = 'option-badge option-chosen-correct'
                badge.textContent = 'Your answer'
                optLi.appendChild(badge)
              }
              opts.appendChild(optLi)
            })

            // if not attempted, show note
            if (!userChoice) {
              const note = document.createElement('div')
              note.className = 'not-attempted'
              note.textContent = 'Not attempted'
              li.appendChild(note)
            }

            li.appendChild(opts)
            qList.appendChild(li)
          })
          body.appendChild(qList)

          // close handler
          modal.querySelector('.summary-close').addEventListener('click', () => overlay.remove())
          overlay.addEventListener('click', (e) => { if (e.target === overlay) overlay.remove() })
        } catch (err) {
          console.warn('Failed to render summary', err)
        }
      })

      btn.addEventListener('click', () => {
        // Build the summary data once
        const totalQuestions = total || (quizState?.questions?.length || 0)
        const attempted = answersSelected.filter(Boolean).length || 0
        const correct = score || 0
        const incorrect = Math.max(0, attempted - correct)
        const role = quizState?.role || ''
        const difficulty = quizState?.difficulty || ''
        const percent = totalQuestions ? Math.round((correct / totalQuestions) * 100) : 0
        const questions = quizState?.questions || []

  const generatePdf = async () => {
          // helper to load script dynamically
          const loadScript = (src) => new Promise((resolve, reject) => {
            if (document.querySelector(`script[src="${src}"]`)) return resolve()
            const s = document.createElement('script')
            s.src = src
            s.onload = () => resolve()
            s.onerror = (e) => reject(e)
            document.head.appendChild(s)
          })

          try {
            // ensure jsPDF constructor is available
            let jsPDFCtor = (window.jspdf && window.jspdf.jsPDF) || window.jsPDF || (window.jspdf && window.jspdf.default && window.jspdf.default.jsPDF)
            if (typeof jsPDFCtor !== 'function') {
              // try to load from CDN
              const jsPdfSrc = 'https://cdn.jsdelivr.net/npm/jspdf@2.5.1/dist/jspdf.umd.min.js'
              await loadScript(jsPdfSrc).catch(() => {})
              jsPDFCtor = (window.jspdf && window.jspdf.jsPDF) || window.jsPDF || (window.jspdf && window.jspdf.default && window.jspdf.default.jsPDF)
            }
            if (typeof jsPDFCtor !== 'function') throw new Error('jsPDF not found')

            // try to capture the pie chart as image using html2canvas if available
            let pieImageData = null
            try {
              if (typeof window.html2canvas !== 'function') {
                // attempt to load html2canvas
                await loadScript('https://cdnjs.cloudflare.com/ajax/libs/html2canvas/1.4.1/html2canvas.min.js').catch(() => {})
              }
              if (typeof window.html2canvas === 'function') {
                const pieEl = document.querySelector('.result-pie')
                if (pieEl) {
                  const canvas = await window.html2canvas(pieEl, { backgroundColor: null, scale: 2 })
                  pieImageData = canvas.toDataURL('image/png')
                }
              }
            } catch (e) {
              console.warn('html2canvas failed, pie image will be omitted', e)
            }

            const doc = new jsPDFCtor({ unit: 'pt', format: 'a4' })
            const pageWidth = doc.internal.pageSize.getWidth()
            const pageHeight = doc.internal.pageSize.getHeight()
            const margin = 48

            // Helper: draw key/value pair with value right-aligned
            const drawKV = (label, value, yPos, valueColor) => {
              doc.setFont('helvetica', 'normal')
              doc.setFontSize(12)
              doc.setTextColor(80, 88, 100)
              doc.text(label, margin, yPos)
              doc.setFont('helvetica', 'bold')
              if (valueColor) doc.setTextColor(...valueColor)
              const valueStr = String(value)
              const valueWidth = doc.getTextWidth(valueStr)
              doc.text(valueStr, pageWidth - margin - valueWidth, yPos)
              // reset color
              doc.setTextColor(80, 88, 100)
            }

            // Cover page
            doc.setFillColor(18, 31, 56)
            doc.rect(0, 0, pageWidth, 140, 'F')
            doc.setTextColor(255, 255, 255)
            doc.setFont('helvetica', 'bold')
            doc.setFontSize(34)
            doc.text('IntervBot', margin, 80)
            doc.setFontSize(11)
            doc.setFont('helvetica', 'normal')
            const participant = quizState?.userName || quizState?.user || 'Participant'
            const now = new Date().toLocaleString()
            doc.text(`Participant: ${participant}`, margin, 104)
            doc.text(`Generated: ${now}`, margin, 120)
            // pie on cover (center-right)
            if (pieImageData) {
              const imgW = 120
              const imgH = 120
              doc.addImage(pieImageData, 'PNG', pageWidth - margin - imgW, 12, imgW, imgH)
            }

            // Summary: render on the same page below the cover header
            doc.setFont('helvetica', 'bold')
            doc.setFontSize(18)
            doc.setTextColor(18, 24, 39)
            const summaryStartY = 160
            doc.text('Quiz Summary', margin, summaryStartY)
            // divider
            doc.setDrawColor(220)
            doc.setLineWidth(0.5)
            doc.line(margin, summaryStartY + 6, pageWidth - margin, summaryStartY + 6)

            let y = summaryStartY + 28
            const rowGap = 28

            drawKV('Total Questions', totalQuestions, y)
            y += rowGap
            drawKV('Attempted', attempted, y)
            y += rowGap
            drawKV('Right', correct, y)
            y += rowGap
            drawKV('Incorrect', incorrect, y)
            y += rowGap
            drawKV('Total Result (%)', `${percent}%`, y, [6, 95, 70])
            y += rowGap
            drawKV('Role', role || 'N/A', y)
            y += rowGap
            drawKV('Difficulty', difficulty || 'N/A', y)

            // Footer: single page number
            doc.setFontSize(10)
            doc.setTextColor(140)
            doc.text(`1 / 1`, pageWidth - margin, pageHeight - 30, { align: 'right' })

            const ts = new Date().toISOString().replace(/[:.]/g, '-')
            doc.save(`quiz_result_${ts}.pdf`)
          } catch (err) {
            console.warn('Failed to generate PDF:', err)
            // fallback to text download
            const fallback = []
            fallback.push('Quiz Result Summary')
            fallback.push('-------------------')
            fallback.push(`Total Questions: ${totalQuestions}`)
            fallback.push(`Attempted Questions: ${attempted}`)
            fallback.push(`Right Questions: ${correct}`)
            fallback.push(`Incorrect Questions: ${incorrect}`)
            fallback.push(`Total Result: ${percent}%`)
            fallback.push(`Role: ${role}`)
            fallback.push(`Difficulty: ${difficulty}`)
            const blob = new Blob([fallback.join('\n')], { type: 'text/plain' })
            const url = URL.createObjectURL(blob)
            const a = document.createElement('a')
            a.href = url
            const ts = new Date().toISOString().replace(/[:.]/g, '-')
            a.download = `quiz_result_${ts}.txt`
            document.body.appendChild(a)
            a.click()
            setTimeout(() => { document.body.removeChild(a); URL.revokeObjectURL(url) }, 150)
          }
        }

        // If jsPDF is present, generate immediately; otherwise try loading it dynamically then generate
        const hasJsPdf = !!((window.jspdf && window.jspdf.jsPDF) || window.jsPDF)
        if (hasJsPdf) {
          generatePdf()
          return
        }

        // Dynamically load jsPDF if not present
        const scriptSrc = 'https://cdn.jsdelivr.net/npm/jspdf@2.5.1/dist/jspdf.umd.min.js'
        const existingScript = document.querySelector(`script[src="${scriptSrc}"]`)
        if (existingScript) {
          existingScript.addEventListener('load', generatePdf)
          existingScript.addEventListener('error', generatePdf)
          return
        }
        const s = document.createElement('script')
        s.src = scriptSrc
        s.onload = generatePdf
        s.onerror = generatePdf
        document.head.appendChild(s)
      })
    } catch (e) {
      console.warn('Failed to attach download button', e)
    }
  }

  document.addEventListener('DOMContentLoaded', () => {
    submitButtonEl = document.getElementById('submit-quiz-btn')
    retakeButtonEl = document.getElementById('retake-quiz-btn')
    resultContainerEl = document.getElementById('quiz-result')
    timerContainerEl = document.getElementById('quiz-timer')

    updateQuizTimerDisplay()
    renderQuiz()

    if (!submitButtonEl || !retakeButtonEl || !resultContainerEl) {
      return
    }

    submitButtonEl.addEventListener('click', () => {
      if (isLocked) return
      if (!quizState || !Array.isArray(quizState.questions) || !quizState.questions.length) return
      showConfirm(() => completeQuizSubmission({ reason: 'manual' }))
    })

    retakeButtonEl.addEventListener('click', () => {
      clearQuizTimer()
      localStorage.removeItem('quizData')
      if (typeof retakeButtonEl.__gooStopIntro === 'function') {
        retakeButtonEl.__gooStopIntro()
      }
      window.location.href = '/landing'
    })
  })

  window.addEventListener('beforeunload', clearQuizTimer)
})()

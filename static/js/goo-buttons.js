// Shared goo-button interactions extracted for reuse on quiz page.
;(function () {
  const buttonMagnetConfig = { radius: 140, strength: 0.62, maxOffset: 28 }

  const setupGooButton = (button) => {
    if (!button || button.dataset.gooInit === 'true') return
    button.dataset.gooInit = 'true'

    const updateGlowPosition = (event) => {
      const rect = button.getBoundingClientRect()
      if (!rect.width || !rect.height) return
      const relativeX = ((event.clientX - rect.left) / rect.width) * 100
      const relativeY = ((event.clientY - rect.top) / rect.height) * 100
      button.style.setProperty('--x', relativeX)
      button.style.setProperty('--y', relativeY)
    }
    button.addEventListener('pointermove', updateGlowPosition)

    let introHandle = null
    const stopIntro = () => {
      if (introHandle !== null) {
        clearInterval(introHandle)
        introHandle = null
      }
      button.style.setProperty('--a', '')
    }
    const startIntro = () => {
      // keep reference for compatibility; no auto intro to prevent idle glow
      stopIntro()
    }

    const targetMagnet = { x: 0, y: 0 }
    const currentMagnet = { x: 0, y: 0 }
    const smoothing = 0.18
    let pendingPointer = null
    let magnetFrame = null
    let smoothFrame = null

    const applyMagnetStyles = () => {
      button.style.setProperty('--mag-x', `${currentMagnet.x.toFixed(2)}px`)
      button.style.setProperty('--mag-y', `${currentMagnet.y.toFixed(2)}px`)
    }

    const ensureSmoothFrame = () => {
      if (smoothFrame !== null) return
      const step = () => {
        const dx = targetMagnet.x - currentMagnet.x
        const dy = targetMagnet.y - currentMagnet.y
        currentMagnet.x += dx * smoothing
        currentMagnet.y += dy * smoothing
        if (Math.abs(dx) < 0.1 && Math.abs(dy) < 0.1) {
          currentMagnet.x = targetMagnet.x
          currentMagnet.y = targetMagnet.y
        }
        applyMagnetStyles()
        if (currentMagnet.x === targetMagnet.x && currentMagnet.y === targetMagnet.y) {
          smoothFrame = null
          return
        }
        smoothFrame = requestAnimationFrame(step)
      }
      smoothFrame = requestAnimationFrame(step)
    }

    const resetMagnet = () => {
      pendingPointer = null
      targetMagnet.x = 0
      targetMagnet.y = 0
      ensureSmoothFrame()
    }

    const clearAnimationFrames = () => {
      if (magnetFrame !== null) {
        cancelAnimationFrame(magnetFrame)
        magnetFrame = null
      }
      if (smoothFrame !== null) {
        cancelAnimationFrame(smoothFrame)
        smoothFrame = null
      }
    }

    const quickReset = () => {
      clearAnimationFrames()
      pendingPointer = null
      targetMagnet.x = 0
      targetMagnet.y = 0
      currentMagnet.x = 0
      currentMagnet.y = 0
      button.style.setProperty('--mag-x', '0px')
      button.style.setProperty('--mag-y', '0px')
      button.style.setProperty('--hover-y', '0px')
      button.style.setProperty('--hover-scale', '1')
    }

    const refreshVisualState = () => {
      quickReset()
      stopIntro()
    }

    const applyMagnet = () => {
      magnetFrame = null
      if (!pendingPointer) return
      const { clientX, clientY } = pendingPointer
      pendingPointer = null
      if (!button.isConnected || button.offsetParent === null) {
        targetMagnet.x = 0
        targetMagnet.y = 0
        ensureSmoothFrame()
        return
      }
      const rect = button.getBoundingClientRect()
      if (!rect.width || !rect.height) {
        targetMagnet.x = 0
        targetMagnet.y = 0
        ensureSmoothFrame()
        return
      }
      const centerX = rect.left + rect.width / 2
      const centerY = rect.top + rect.height / 2
      const dx = clientX - centerX
      const dy = clientY - centerY
      const distance = Math.hypot(dx, dy)
      const relX = ((clientX - rect.left) / rect.width) * 100
      const relY = ((clientY - rect.top) / rect.height) * 100
      button.style.setProperty('--x', relX)
      button.style.setProperty('--y', relY)
      if (distance > buttonMagnetConfig.radius) {
        targetMagnet.x = 0
        targetMagnet.y = 0
        ensureSmoothFrame()
        return
      }
      const normalized = 1 - distance / buttonMagnetConfig.radius
      const pull = normalized * buttonMagnetConfig.strength
      targetMagnet.x = Math.max(Math.min(dx * pull, buttonMagnetConfig.maxOffset), -buttonMagnetConfig.maxOffset)
      targetMagnet.y = Math.max(Math.min(dy * pull, buttonMagnetConfig.maxOffset), -buttonMagnetConfig.maxOffset)
      ensureSmoothFrame()
    }

    const scheduleMagnet = (event) => {
      pendingPointer = { clientX: event.clientX, clientY: event.clientY }
      if (magnetFrame === null) magnetFrame = requestAnimationFrame(applyMagnet)
    }

    const magnetEnabled = button.getAttribute('data-goo-magnet') !== 'off'

    refreshVisualState()
    button.addEventListener('pointerover', stopIntro)

    if (magnetEnabled) {
      window.addEventListener('pointermove', scheduleMagnet, { passive: true })
      window.addEventListener('pointerleave', resetMagnet, { passive: true })
      button.addEventListener('pointerout', resetMagnet)
      button.addEventListener('pointerup', resetMagnet)
      applyMagnetStyles()
    } else {
      // Ensure no magnet offset is applied
      button.style.setProperty('--mag-x', '0px')
      button.style.setProperty('--mag-y', '0px')
    }

    button.__gooStartIntro = startIntro
    button.__gooStopIntro = stopIntro
    button.__gooQuickReset = quickReset
    button.__gooResetMagnet = resetMagnet
    button.__gooRefresh = refreshVisualState

    const observer = new MutationObserver((mutations) => {
      for (const mutation of mutations) {
        if (mutation.type === 'attributes' || mutation.type === 'childList') {
          refreshVisualState()
          break
        }
      }
    })
    observer.observe(button, { attributes: true, attributeFilter: ['disabled'], childList: true, subtree: false })
    button.__gooObserver = observer
  }

  const refreshAll = (root) => {
    const scope = root || document
    const targets = scope.querySelectorAll ? scope.querySelectorAll('.goo-button') : []
    targets.forEach(setupGooButton)
    if (root && root.matches && root.matches('.goo-button')) {
      setupGooButton(root)
    }
  }

  refreshAll()
  window.ivRefreshGooButtons = refreshAll
})()

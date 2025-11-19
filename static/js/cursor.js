(function () {
    const prefersReducedMotion = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    const hasCoarsePointer = window.matchMedia && window.matchMedia('(pointer: coarse)').matches;

    if (prefersReducedMotion || hasCoarsePointer) {
        return;
    }

    const LIGHT_CURSOR_COLOR = '#111827';
    const DARK_CURSOR_COLOR = '#b1f02b';
    const CURSOR_STORAGE_KEY = 'ivCursorLastPos';

    const SPRING_CONFIG = {
        damping: 42,
        stiffness: 420,
        mass: 1,
        restDelta: 0.0005,
        restSpeed: 0.004
    };

    const ROTATION_SPRING_CONFIG = {
        damping: 48,
        stiffness: 320,
        mass: 1,
        restDelta: 0.0005,
        restSpeed: 0.004
    };

    const SCALE_SPRING_CONFIG = {
        damping: 36,
        stiffness: 480,
        mass: 1,
        restDelta: 0.0005,
        restSpeed: 0.004
    };

    const SPEED_THRESHOLD = 45; // pixels per second
    const MOVING_SCALE = 0.94;
    const SCALE_RESET_DELAY = 140; // ms
    const MAX_DELTA_SECONDS = 0.014; // clamp to ~70fps for quicker response

    function getActiveTheme() {
        const theme = document.body && document.body.dataset ? document.body.dataset.theme : null;
        return theme === 'theme-dark' ? 'theme-dark' : 'theme-light';
    }

    function getCursorColor() {
        return getActiveTheme() === 'theme-dark' ? DARK_CURSOR_COLOR : LIGHT_CURSOR_COLOR;
    }

    function clamp(value, min, max) {
        return Math.min(Math.max(value, min), max);
    }

    function storePointerPosition(x, y) {
        try {
            const clampedX = clamp(x, 0, Math.max(window.innerWidth, 0));
            const clampedY = clamp(y, 0, Math.max(window.innerHeight, 0));
            sessionStorage.setItem(CURSOR_STORAGE_KEY, JSON.stringify({ x: clampedX, y: clampedY }));
        } catch (_) {
            // ignore storage errors (e.g., private mode)
        }
    }

    function readPointerPosition() {
        try {
            const raw = sessionStorage.getItem(CURSOR_STORAGE_KEY);
            if (!raw) {
                return null;
            }
            const parsed = JSON.parse(raw);
            if (typeof parsed?.x === 'number' && typeof parsed?.y === 'number') {
                return {
                    x: clamp(parsed.x, 0, Math.max(window.innerWidth, 0)),
                    y: clamp(parsed.y, 0, Math.max(window.innerHeight, 0))
                };
            }
        } catch (_) {
            // ignore parse/storage errors
        }
        return null;
    }

    function createSpring(initial, config) {
        let value = initial;
        let target = initial;
        let velocity = 0;

        const api = {
            setTarget(nextTarget) {
                target = nextTarget;
            },
            jump(nextValue) {
                value = nextValue;
                target = nextValue;
                velocity = 0;
            },
            step(deltaSeconds) {
                const displacement = target - value;
                const springForce = config.stiffness * displacement;
                const dampingForce = config.damping * velocity;
                const acceleration = (springForce - dampingForce) / config.mass;

                velocity += acceleration * deltaSeconds;
                value += velocity * deltaSeconds;

                const isAtRest = Math.abs(velocity) <= config.restSpeed && Math.abs(target - value) <= config.restDelta;
                if (isAtRest) {
                    value = target;
                    velocity = 0;
                }

                return value;
            },
            get value() {
                return value;
            },
            get velocity() {
                return velocity;
            }
        };

        return api;
    }

    function createCursorElement(initialColor) {
        const wrapper = document.createElement('div');
        wrapper.setAttribute('data-smooth-cursor', '');
        wrapper.setAttribute('aria-hidden', 'true');
        wrapper.style.position = 'fixed';
        wrapper.style.left = '0';
        wrapper.style.top = '0';
        wrapper.style.pointerEvents = 'none';
        wrapper.style.zIndex = '10000';
        wrapper.style.transform = 'translate3d(-50%, -50%, 0)';
        wrapper.style.willChange = 'transform';
        wrapper.style.transition = 'opacity 0.2s ease';
        wrapper.style.opacity = '0';

        wrapper.innerHTML = '<svg xmlns="http://www.w3.org/2000/svg" width="50" height="54" viewBox="0 0 50 54" fill="none" style="transform: scale(0.5); transform-origin: center; display: block;">'
            + '<g filter="url(#filter0_d_91_7928)">'
            + '<path data-cursor-shape="true" d="M42.6817 41.1495L27.5103 6.79925C26.7269 5.02557 24.2082 5.02558 23.3927 6.79925L7.59814 41.1495C6.75833 42.9759 8.52712 44.8902 10.4125 44.1954L24.3757 39.0496C24.8829 38.8627 25.4385 38.8627 25.9422 39.0496L39.8121 44.1954C41.6849 44.8902 43.4884 42.9759 42.6817 41.1495Z" fill="' + initialColor + '" />'
            + '</g>'
            + '<defs>'
            + '<filter id="filter0_d_91_7928" x="0.602397" y="0.952444" width="49.0584" height="52.428" filterUnits="userSpaceOnUse" color-interpolation-filters="sRGB">'
            + '<feFlood flood-opacity="0" result="BackgroundImageFix" />'
            + '<feColorMatrix in="SourceAlpha" type="matrix" values="0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 127 0" result="hardAlpha" />'
            + '<feOffset dy="2.25825" />'
            + '<feGaussianBlur stdDeviation="2.25825" />'
            + '<feComposite in2="hardAlpha" operator="out" />'
            + '<feColorMatrix type="matrix" values="0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0.08 0" />'
            + '<feBlend mode="normal" in2="BackgroundImageFix" result="effect1_dropShadow_91_7928" />'
            + '<feBlend mode="normal" in="SourceGraphic" in2="effect1_dropShadow_91_7928" result="shape" />'
            + '</filter>'
            + '</defs>'
            + '</svg>';

        const shapePath = wrapper.querySelector('[data-cursor-shape]');

        return {
            wrapper,
            setColor(nextColor) {
                if (shapePath) {
                    shapePath.setAttribute('fill', nextColor);
                }
            }
        };
    }

    function init() {
        if (!document.body) {
            return;
        }

        if (document.querySelector('[data-smooth-cursor]')) {
            return;
        }

        const cursorColor = getCursorColor();
        const { wrapper: cursor, setColor: setCursorColor } = createCursorElement(cursorColor);
        document.body.appendChild(cursor);
        setCursorColor(cursorColor);
        document.body.classList.add('has-smooth-cursor');

        const storedPosition = readPointerPosition();
        let pointerX = storedPosition ? storedPosition.x : window.innerWidth / 2;
        let pointerY = storedPosition ? storedPosition.y : window.innerHeight / 2;
        storePointerPosition(pointerX, pointerY);

        const cursorX = createSpring(pointerX, SPRING_CONFIG);
        const cursorY = createSpring(pointerY, SPRING_CONFIG);
        const rotationSpring = createSpring(0, ROTATION_SPRING_CONFIG);
        const scaleSpring = createSpring(1, SCALE_SPRING_CONFIG);

        cursorX.jump(pointerX);
        cursorY.jump(pointerY);
        rotationSpring.jump(0);
        scaleSpring.jump(1);
        cursor.style.transform = 'translate3d(' + pointerX + 'px, ' + pointerY + 'px, 0) translate(-50%, -50%) rotate(0deg) scale(1)';

        let lastTime = performance.now();

        let previousAngle = 0;
        let accumulatedRotation = 0;
        let hasAngle = false;
        let scaleTimeoutId = null;
        let isHidden = true;
        let isCleaned = false;
        const handleThemeChange = (event) => {
            const theme = event && event.detail ? event.detail.theme : null;
            if (theme === 'theme-dark') {
                setCursorColor(DARK_CURSOR_COLOR);
            } else if (theme === 'theme-light') {
                setCursorColor(LIGHT_CURSOR_COLOR);
            } else {
                setCursorColor(getCursorColor());
            }
        };

        document.addEventListener('iv-theme-change', handleThemeChange);

        function showCursor() {
            if (isHidden) {
                cursor.style.opacity = '1';
                isHidden = false;
            }
        }

        function hideCursor() {
            if (!isHidden) {
                cursor.style.opacity = '0';
                isHidden = true;
            }
        }

        function onMouseMove(event) {
            pointerX = event.clientX;
            pointerY = event.clientY;
            storePointerPosition(pointerX, pointerY);
            showCursor();
        }

        function onPointerDown(event) {
            pointerX = event.clientX;
            pointerY = event.clientY;
            storePointerPosition(pointerX, pointerY);
            showCursor();
        }

        function onMouseLeave() {
            hideCursor();
        }

        function onVisibilityChange() {
            if (document.visibilityState === 'hidden') {
                hideCursor();
            }
        }

        window.addEventListener('mousemove', onMouseMove);
        window.addEventListener('pointerdown', onPointerDown, { passive: true });
        window.addEventListener('mouseleave', onMouseLeave);
        document.addEventListener('visibilitychange', onVisibilityChange);

        showCursor();

        function cleanup() {
            if (isCleaned) {
                return;
            }
            isCleaned = true;
            window.removeEventListener('mousemove', onMouseMove);
            window.removeEventListener('mouseleave', onMouseLeave);
            window.removeEventListener('pointerdown', onPointerDown);
            window.removeEventListener('beforeunload', cleanup);
            window.removeEventListener('pagehide', pageHideHandler);
            document.removeEventListener('visibilitychange', onVisibilityChange);
            document.removeEventListener('iv-theme-change', handleThemeChange);
            storePointerPosition(pointerX, pointerY);
            if (cursor.parentElement) {
                cursor.parentElement.removeChild(cursor);
            }
            document.body.classList.remove('has-smooth-cursor');
            if (scaleTimeoutId) {
                clearTimeout(scaleTimeoutId);
            }
        }

        function pageHideHandler() {
            cleanup();
        }

        window.addEventListener('beforeunload', cleanup);
        window.addEventListener('pagehide', pageHideHandler);

        function animate(now) {
            if (isCleaned) {
                return;
            }
            const deltaSeconds = Math.min((now - lastTime) / 1000, MAX_DELTA_SECONDS);
            lastTime = now;

            cursorX.setTarget(pointerX);
            cursorY.setTarget(pointerY);

            const currentX = cursorX.step(deltaSeconds);
            const currentY = cursorY.step(deltaSeconds);

            const velX = cursorX.velocity;
            const velY = cursorY.velocity;
            const speed = Math.sqrt(velX * velX + velY * velY);

            if (speed > SPEED_THRESHOLD) {
                const currentAngle = Math.atan2(velY, velX) * (180 / Math.PI) + 90;
                if (!hasAngle) {
                    previousAngle = currentAngle;
                    accumulatedRotation = currentAngle;
                    rotationSpring.jump(accumulatedRotation);
                    hasAngle = true;
                }

                let angleDiff = currentAngle - previousAngle;
                if (angleDiff > 180) angleDiff -= 360;
                if (angleDiff < -180) angleDiff += 360;
                accumulatedRotation += angleDiff;
                rotationSpring.setTarget(accumulatedRotation);
                previousAngle = currentAngle;

                scaleSpring.setTarget(MOVING_SCALE);
                if (scaleTimeoutId) {
                    clearTimeout(scaleTimeoutId);
                }
                scaleTimeoutId = window.setTimeout(() => {
                    scaleSpring.setTarget(1);
                }, SCALE_RESET_DELAY);
            }

            const currentRotation = rotationSpring.step(deltaSeconds);
            const currentScale = scaleSpring.step(deltaSeconds);

            cursor.style.transform = 'translate3d(' + currentX + 'px, ' + currentY + 'px, 0) translate(-50%, -50%) rotate(' + currentRotation + 'deg) scale(' + currentScale + ')';

            requestAnimationFrame(animate);
        }

        requestAnimationFrame((time) => {
            lastTime = time;
            animate(time);
        });
    }

    window.addEventListener('pageshow', (event) => {
        if (event.persisted || !document.querySelector('[data-smooth-cursor]')) {
            init();
        }
    });

    if (document.readyState === 'complete' || document.readyState === 'interactive') {
        init();
    } else {
        document.addEventListener('DOMContentLoaded', init);
    }
})();

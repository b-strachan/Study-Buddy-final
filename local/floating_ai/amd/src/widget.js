define([], function() {
    'use strict';

    const createIframe = (container, courseId) => {
        const iframe = document.createElement('iframe');
        iframe.className = 'local-floating-ai__iframe';
        iframe.setAttribute('title', 'AI chat');
        iframe.setAttribute('loading', 'eager');
        iframe.setAttribute('referrerpolicy', 'same-origin');
        iframe.src = M.cfg.wwwroot + '/local/floating_ai/launch.php?courseid=' + encodeURIComponent(courseId);

        container.innerHTML = '';
        container.appendChild(iframe);
    };

    const init = (config) => {
        const root = document.getElementById(config.rootid || 'local-floating-ai-root');

        if (!root) {
            return;
        }

        root.dataset.pluginState = 'loaded';
        root.setAttribute('data-plugin-loaded', 'true');
        window.localFloatingAiStatus = {
            loaded: true,
            courseId: config.courseid,
        };

        // This gives an immediate, inspectable signal in DevTools.
        console.info('local_floating_ai widget loaded', { courseId: config.courseid });

        const toggle = root.querySelector('[data-role="toggle"]');
        const close = root.querySelector('[data-role="close"]');
        const panel = root.querySelector('[data-role="panel"]');
        const body = root.querySelector('[data-role="body"]');
        const placeholder = root.querySelector('[data-role="placeholder"]');
        let iframeLoaded = false;

        if (config.buttonlabel) {
            toggle.textContent = config.buttonlabel;
        }

        if (config.closelabel) {
            close.textContent = config.closelabel;
        }

        if (config.loadingtext && placeholder) {
            placeholder.textContent = config.loadingtext;
        }

        const setOpenState = (isopen) => {
            root.classList.toggle('is-open', isopen);
            panel.hidden = !isopen;
            toggle.setAttribute('aria-expanded', isopen ? 'true' : 'false');
        };

        const openPanel = () => {
            setOpenState(true);

            if (!iframeLoaded) {
                createIframe(body, config.courseid);
                iframeLoaded = true;
            }
        };

        const closePanel = () => {
            setOpenState(false);
        };

        toggle.addEventListener('click', () => {
            if (root.classList.contains('is-open')) {
                closePanel();
                return;
            }

            openPanel();
        });

        close.addEventListener('click', closePanel);

        document.addEventListener('keydown', (event) => {
            if (event.key === 'Escape' && root.classList.contains('is-open')) {
                closePanel();
            }
        });
    };

    return {
        init: init,
    };
});
/**
 * Simple notification system
 *
 * Usage:
 *   const notifier = Notifier({time: 3000, classes: "my-positioning"})
 *   notifier.success("Task added successfully")
 *   notifier.error("Something went wrong")
 *
 *   // Persistent notification (stays until closed)
 *   const persistentNotifier = Notifier({time: null})
 *   persistentNotifier.info("This stays until you close it")
 */

export function Notifier(options = {}) {
    const defaults = {
        time: 3000,
        classes: ''
    };

    const config = { ...defaults, ...options };

    function removeNotification(notification) {
        notification.classList.remove('notifier-visible');
        notification.classList.add('notifier-hiding');

        // Remove from DOM after transition
        setTimeout(() => {
            if (notification.parentNode) {
                notification.parentNode.removeChild(notification);
            }
        }, 300);
    }

    function show(message, type = 'info') {
        const notification = document.createElement('div');
        notification.className = `notifier notifier-${type} ${config.classes}`;

        const messageSpan = document.createElement('span');
        messageSpan.className = 'notifier-message';
        messageSpan.textContent = message;

        const closeButton = document.createElement('button');
        closeButton.className = 'notifier-close';
        closeButton.innerHTML = '&times;';
        closeButton.setAttribute('aria-label', 'Close notification');
        closeButton.addEventListener('click', () => {
            removeNotification(notification);
        });

        notification.appendChild(messageSpan);
        notification.appendChild(closeButton);

        document.body.appendChild(notification);

        // Trigger reflow to enable CSS transition
        notification.offsetHeight;

        // Add visible class for fade-in
        notification.classList.add('notifier-visible');

        // Auto-dismiss after specified time (if time is not null)
        if (config.time !== null) {
            setTimeout(() => {
                removeNotification(notification);
            }, config.time);
        }
    }

    return {
        success: (message) => show(message, 'success'),
        error: (message) => show(message, 'error'),
        info: (message) => show(message, 'info'),
        warning: (message) => show(message, 'warning')
    };
}

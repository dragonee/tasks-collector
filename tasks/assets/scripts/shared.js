// Shared utilities (e.g. CSRF token injector).

function max_count(days) {
    let maxCount = 0;
    for (let day of days) {
        const count = parseInt(day.getAttribute('data-count'), 10);
        if (count > maxCount) {
            maxCount = count;
        }
    }
    return maxCount;
}

function interpolate_color(color_from, color_to, ratio) {
    const r = Math.round(color_from[0] + ratio * (color_to[0] - color_from[0]));
    const g = Math.round(color_from[1] + ratio * (color_to[1] - color_from[1]));
    const b = Math.round(color_from[2] + ratio * (color_to[2] - color_from[2]));
    return `rgb(${r}, ${g}, ${b})`;
}

function hex_to_rgb(hex) {
    const result = /^#?([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i.exec(hex);
    return result ? [parseInt(result[1], 16), parseInt(result[2], 16), parseInt(result[3], 16)] : null;
}

function colorize_single_calendar(days, color_from, color_to) {
    const maxCount = max_count(days);

    const color_from_rgb = hex_to_rgb(color_from);
    const color_to_rgb = hex_to_rgb(color_to);

    for (let day of days) {
        const count = parseInt(day.getAttribute('data-count'), 10);
        if (count == 0) {
            continue;
        }

        const color = interpolate_color(color_from_rgb, color_to_rgb, count / maxCount);
        day.style.backgroundColor = color;
    }
}

function colorize_calendar(cls, color_from, color_to) {
    const calendars = document.getElementsByClassName(cls);

    for (let calendar of calendars) {
        const days = calendar.querySelectorAll('.event-day');
        colorize_single_calendar(days, color_from, color_to);
    }
}

document.addEventListener('DOMContentLoaded', () => {
    colorize_calendar('calendar', '#b2edac', '#3b6f2c');
})
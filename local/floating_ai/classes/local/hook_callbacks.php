<?php
// This file is part of Moodle - http://moodle.org/
//
// Moodle is free software: you can redistribute it and/or modify
// it under the terms of the GNU General Public License as published by
// the Free Software Foundation, either version 3 of the License, or
// (at your option) any later version.

namespace local_floating_ai\local;

defined('MOODLE_INTERNAL') || die();

/**
 * Hook callbacks for local_floating_ai.
 *
 * @package   local_floating_ai
 */
class hook_callbacks {
    /**
     * Inject the floating AI widget before standard footer HTML.
     *
     * @param \core\hook\output\before_standard_footer_html $hook
     * @return void
     */
    public static function before_standard_footer_html(\core\hook\output\before_standard_footer_html $hook): void {
        global $PAGE;

        if ((defined('CLI_SCRIPT') && CLI_SCRIPT) || (defined('AJAX_SCRIPT') && AJAX_SCRIPT) || empty($PAGE) || empty($PAGE->course) || empty($PAGE->course->id)) {
            return;
        }

        $courseid = (int)$PAGE->course->id;

        $PAGE->requires->css(new \moodle_url('/local/floating_ai/styles.css'));
        $PAGE->requires->js_call_amd('local_floating_ai/widget', 'init', [
            [
                'courseid' => $courseid,
                'rootid' => 'local-floating-ai-root',
                'buttonlabel' => get_string('openchat', 'local_floating_ai'),
                'closelabel' => get_string('closechat', 'local_floating_ai'),
                'widgettitle' => get_string('widgettitle', 'local_floating_ai'),
                'loadingtext' => get_string('loading', 'local_floating_ai'),
            ],
        ]);

        $html = \html_writer::start_tag('div', [
            'id' => 'local-floating-ai-root',
            'class' => 'local-floating-ai',
            'data-courseid' => $courseid,
        ]);

        $html .= \html_writer::tag('button', get_string('openchat', 'local_floating_ai'), [
            'type' => 'button',
            'class' => 'local-floating-ai__toggle',
            'data-role' => 'toggle',
            'aria-expanded' => 'false',
            'aria-controls' => 'local-floating-ai-panel',
        ]);

        $html .= \html_writer::tag('span', get_string('pluginloaded', 'local_floating_ai'), [
            'class' => 'local-floating-ai__status',
            'data-role' => 'status',
            'title' => get_string('pluginloaded_help', 'local_floating_ai'),
        ]);

        $html .= \html_writer::start_tag('section', [
            'id' => 'local-floating-ai-panel',
            'class' => 'local-floating-ai__panel',
            'data-role' => 'panel',
            'hidden' => 'hidden',
            'aria-label' => get_string('widgettitle', 'local_floating_ai'),
        ]);

        $html .= \html_writer::start_tag('header', ['class' => 'local-floating-ai__header']);
        $html .= \html_writer::tag('h2', get_string('widgettitle', 'local_floating_ai'), ['class' => 'local-floating-ai__title']);
        $html .= \html_writer::tag('button', get_string('closechat', 'local_floating_ai'), [
            'type' => 'button',
            'class' => 'local-floating-ai__close',
            'data-role' => 'close',
            'aria-label' => get_string('closechat', 'local_floating_ai'),
        ]);
        $html .= \html_writer::end_tag('header');

        $html .= \html_writer::start_tag('div', [
            'class' => 'local-floating-ai__body',
            'data-role' => 'body',
        ]);
        $html .= \html_writer::tag('div', get_string('loading', 'local_floating_ai'), [
            'class' => 'local-floating-ai__placeholder',
            'data-role' => 'placeholder',
        ]);
        $html .= \html_writer::end_tag('div');

        $html .= \html_writer::end_tag('section');
        $html .= \html_writer::end_tag('div');

        $hook->add_html($html);
    }
}

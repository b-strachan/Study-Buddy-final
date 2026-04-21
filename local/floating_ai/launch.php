<?php
// This file is part of Moodle - http://moodle.org/
//
// Moodle is free software: you can redistribute it and/or modify
// it under the terms of the GNU General Public License as published by
// the Free Software Foundation, either version 3 of the License, or
// (at your option) any later version.

require_once(__DIR__ . '/../../config.php');

global $CFG, $DB, $USER;

$courseid = required_param('courseid', PARAM_INT);
$course = $DB->get_record('course', ['id' => $courseid], '*', MUST_EXIST);
$coursecontext = context_course::instance($course->id);

require_login($course);

\core\session\manager::write_close();

$config = local_floating_ai_get_launch_config();
$launchurl = $config['launchurl'];
$clientid = $config['clientid'];
$issuer = $config['issuer'];
$deploymentid = $config['deploymentid'];
$kid = $config['kid'];
$privatekey = $config['privatekey'];

if (empty($launchurl)) {
    throw new moodle_exception('launchurlnotconfigured', 'local_floating_ai');
}

if (empty($clientid)) {
    throw new moodle_exception('clientidnotconfigured', 'local_floating_ai');
}

if (empty($privatekey)) {
    throw new moodle_exception('privatekeynotconfigured', 'local_floating_ai');
}

$now = time();
$nonce = bin2hex(random_bytes(16));
$state = bin2hex(random_bytes(16));
$subject = hash('sha256', $CFG->wwwroot . '|' . $USER->id);

$jwt = local_floating_ai_build_lti_jwt([
    'iss' => $issuer,
    'sub' => $subject,
    'aud' => $clientid,
    'iat' => $now,
    'exp' => $now + 300,
    'nonce' => $nonce,
    'https://purl.imsglobal.org/spec/lti/claim/deployment_id' => $deploymentid,
    'https://purl.imsglobal.org/spec/lti/claim/message_type' => 'LtiResourceLinkRequest',
    'https://purl.imsglobal.org/spec/lti/claim/version' => '1.3.0',
    'https://purl.imsglobal.org/spec/lti/claim/target_link_uri' => $launchurl,
    'https://purl.imsglobal.org/spec/lti/claim/resource_link' => [
        'id' => 'local-floating-ai-course-' . $course->id,
        'description' => format_string($course->fullname),
    ],
    'https://purl.imsglobal.org/spec/lti/claim/context' => [
        'id' => 'moodle-course-' . $course->id,
        'label' => $course->shortname,
        'title' => format_string($course->fullname),
        'type' => ['http://purl.imsglobal.org/vocab/lis/v2/course#CourseOffering'],
    ],
    'https://purl.imsglobal.org/spec/lti/claim/roles' => local_floating_ai_get_lti_roles($coursecontext, $USER->id),
    'https://purl.imsglobal.org/spec/lti/claim/custom' => [
        'moodle_user_id' => (string)$USER->id,
        'moodle_course_id' => (string)$course->id,
        'moodle_course_shortname' => (string)$course->shortname,
        'moodle_course_fullname' => format_string($course->fullname),
    ],
    'https://purl.imsglobal.org/spec/lti/claim/lis' => [
        'person_sourcedid' => (string)$USER->id,
        'course_section_sourcedid' => (string)$course->id,
    ],
    'name' => fullname($USER),
    'given_name' => $USER->firstname,
    'family_name' => $USER->lastname,
    'email' => $USER->email,
]);

$loginhint = hash('sha256', $subject . '|' . $course->id . '|' . $nonce);
$messagehint = base64_encode(json_encode([
    'courseid' => $course->id,
    'userid' => $USER->id,
], JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE));

header('Content-Type: text/html; charset=utf-8');
header('Cache-Control: no-store, no-cache, must-revalidate, max-age=0');
header('Pragma: no-cache');

echo '<!DOCTYPE html>';
echo '<html lang="en">';
echo '<head>';
echo '<meta charset="utf-8">';
echo '<meta name="viewport" content="width=device-width, initial-scale=1">';
echo '<title>' . s(get_string('widgettitle', 'local_floating_ai')) . '</title>';
echo '</head>';
echo '<body style="margin:0;background:transparent;">';
echo html_writer::start_tag('form', [
    'method' => 'post',
    'action' => $launchurl,
    'target' => '_self',
    'id' => 'local-floating-ai-launch-form',
]);
echo html_writer::empty_tag('input', ['type' => 'hidden', 'name' => 'id_token', 'value' => $jwt]);
echo html_writer::empty_tag('input', ['type' => 'hidden', 'name' => 'login_hint', 'value' => $loginhint]);
echo html_writer::empty_tag('input', ['type' => 'hidden', 'name' => 'lti_message_hint', 'value' => $messagehint]);
echo html_writer::empty_tag('input', ['type' => 'hidden', 'name' => 'target_link_uri', 'value' => $launchurl]);
echo html_writer::empty_tag('input', ['type' => 'hidden', 'name' => 'client_id', 'value' => $clientid]);
echo html_writer::empty_tag('input', ['type' => 'hidden', 'name' => 'state', 'value' => $state]);
echo html_writer::empty_tag('input', ['type' => 'hidden', 'name' => 'nonce', 'value' => $nonce]);
echo html_writer::empty_tag('input', ['type' => 'hidden', 'name' => 'iss', 'value' => $issuer]);
echo html_writer::end_tag('form');
echo '<noscript><p>This launch requires JavaScript.</p></noscript>';
echo '<script>document.getElementById("local-floating-ai-launch-form").submit();</script>';
echo '</body>';
echo '</html>';

/**
 * Returns the launch configuration for the widget.
 *
 * @return array<string, string>
 */
function local_floating_ai_get_launch_config(): array {
    global $CFG;

    $privatekey = get_config('local_floating_ai', 'privatekey');
    if ($privatekey === false || $privatekey === null || $privatekey === '') {
        $privatekeyfile = get_config('local_floating_ai', 'privatekeyfile');
        if (empty($privatekeyfile)) {
            $privatekeyfile = realpath(__DIR__ . '/../../private.key');
        } else if (!preg_match('/^(?:[A-Za-z]:[\\\\\/]|\\\\\\\\|\/)/', $privatekeyfile)) {
            $privatekeyfile = $CFG->dirroot . '/' . ltrim($privatekeyfile, '/\\');
        }

        $privatekey = (!empty($privatekeyfile) && file_exists($privatekeyfile)) ? file_get_contents($privatekeyfile) : '';
    }

    return [
        'launchurl' => (string)(get_config('local_floating_ai', 'launchurl') ?: ($CFG->local_floating_ai_launch_url ?? '')),
        'clientid' => (string)(get_config('local_floating_ai', 'clientid') ?: ($CFG->local_floating_ai_client_id ?? '')),
        'issuer' => (string)(get_config('local_floating_ai', 'issuer') ?: $CFG->wwwroot),
        'deploymentid' => (string)(get_config('local_floating_ai', 'deploymentid') ?: ($CFG->local_floating_ai_deployment_id ?? 'floating-ai-deployment')),
        'kid' => (string)(get_config('local_floating_ai', 'kid') ?: ($CFG->local_floating_ai_kid ?? '')),
        'privatekey' => is_string($privatekey) ? trim($privatekey) : '',
    ];
}

/**
 * Build the signed LTI JWT.
 *
 * @param array<string, mixed> $claims
 * @return string
 */
function local_floating_ai_build_lti_jwt(array $claims): string {
    $config = local_floating_ai_get_launch_config();
    $header = [
        'alg' => 'RS256',
        'typ' => 'JWT',
    ];

    if (!empty($config['kid'])) {
        $header['kid'] = $config['kid'];
    }

    $signinginput = local_floating_ai_base64url_encode(json_encode($header, JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE)) . '.' .
        local_floating_ai_base64url_encode(json_encode($claims, JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE));

    $privatekeyresource = openssl_pkey_get_private($config['privatekey']);
    if ($privatekeyresource === false) {
        throw new moodle_exception('privatekeynotconfigured', 'local_floating_ai');
    }

    $signature = '';
    if (!openssl_sign($signinginput, $signature, $privatekeyresource, OPENSSL_ALGO_SHA256)) {
        throw new moodle_exception('launchfailed', 'local_floating_ai');
    }

    openssl_free_key($privatekeyresource);

    return $signinginput . '.' . local_floating_ai_base64url_encode($signature);
}

/**
 * Encode data using the base64url variant.
 *
 * @param string $data
 * @return string
 */
function local_floating_ai_base64url_encode(string $data): string {
    return rtrim(strtr(base64_encode($data), '+/', '-_'), '=');
}

/**
 * Map Moodle roles to LTI role URIs.
 *
 * @param context $context
 * @param int $userid
 * @return array<int, string>
 */
function local_floating_ai_get_lti_roles(context $context, int $userid): array {
    global $USER;

    $roles = [];

    if (is_siteadmin($USER)) {
        $roles[] = 'http://purl.imsglobal.org/vocab/lis/v2/membership#Administrator';
    } else if (has_capability('moodle/course:update', $context, $userid)) {
        $roles[] = 'http://purl.imsglobal.org/vocab/lis/v2/membership#Instructor';
    } else if (has_capability('moodle/course:view', $context, $userid)) {
        $roles[] = 'http://purl.imsglobal.org/vocab/lis/v2/membership#Learner';
    } else {
        $roles[] = 'http://purl.imsglobal.org/vocab/lis/v2/membership#Member';
    }

    return array_values(array_unique($roles));
}
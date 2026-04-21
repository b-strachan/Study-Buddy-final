<?php
// This file is part of Moodle - http://moodle.org/
//
// Moodle is free software: you can redistribute it and/or modify
// it under the terms of the GNU General Public License as published by
// the Free Software Foundation, either version 3 of the License, or
// (at your option) any later version.

namespace local_floating_ai;

defined('MOODLE_INTERNAL') || die();

require_once(__DIR__ . '/local/hook_callbacks.php');

/**
 * Backwards-compatible hook callback entry point for local_floating_ai.
 *
 * @package   local_floating_ai
 */
class hook_callbacks extends \local_floating_ai\local\hook_callbacks {
}

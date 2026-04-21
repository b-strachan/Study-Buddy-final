<?php
// This file is part of Moodle - http://moodle.org/
//
// Moodle is free software: you can redistribute it and/or modify
// it under the terms of the GNU General Public License as published by
// the Free Software Foundation, either version 3 of the License, or
// (at your option) any later version.

defined('MOODLE_INTERNAL') || die();

/**
 * Upgrade steps for local_floating_ai.
 *
 * @param int $oldversion
 * @return bool
 */
function xmldb_local_floating_ai_upgrade(int $oldversion): bool {
    if ($oldversion < 2026041605) {
        purge_all_caches();
        upgrade_plugin_savepoint(true, 2026041605, 'local', 'floating_ai');
    }

    return true;
}
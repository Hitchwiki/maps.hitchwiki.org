<?php
/*
 * Hitchwiki Maps: log.php
 * For logging events with JS
 */
 
/*
 * Load config to set language and stuff
 */
require_once "../config.php";


if(!isset($_POST["event"]) OR empty($_POST["event"]) OR !isset($_POST["data"]) OR empty($_POST["data"])) {
	echo '{"error": "true"}';
}
else {
	echo '{"success": "true"}';
}

?>
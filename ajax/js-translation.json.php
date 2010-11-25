<?php
/*
 * Hitchwiki Maps: js-translation.json.php
 * Return JSON array of translated strings to use in JavaScript
 * End use requires jQuery Gettext: http://plugins.jquery.com/project/gettext
 */

/*
 * Load config to set language and stuff
 */
require_once "../config.php";

/*
 * Strings to be translated
 */
$strings = array(
	"Toggle log",
	"places",
	"Zoom closer to see them.",
	"Searching...",
	"Your search did not match any places.",
	"Try searching in English and add a country name in to your search.",
	"Example:",
	"Not found",
	"Your search did not match any places.",
	"Try searching by english city names or/and add a country name with cities.",
	"Are you sure you want to remove this comment?",
	"Error"
);

$translated_strings = array();

// Translate all array values using gettext
foreach($strings as $string) {

	$translated_strings[$string] = _($string);

}

echo json_encode($translated_strings);

?>
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
	"Error",
	"Updating description failed.",
	"Please try again!"
);


/*
 * TODO
 * This an array containing to-be translated strings for JS, it needs to be a copy of array above, only closed by _(string)
 * Idea is that poedit will read this file automaticly and add these to the .po file
 * But then, this array isn't used in any other way in this app
 * Thinking some better solution for this...
 */
$poedit = array(
	_("Toggle log"),
	_("places"),
	_("Zoom closer to see them."),
	_("Searching..."),
	_("Your search did not match any places."),
	_("Try searching in English and add a country name in to your search."),
	_("Example:"),
	_("Not found"),
	_("Your search did not match any places."),
	_("Try searching by english city names or/and add a country name with cities."),
	_("Are you sure you want to remove this comment?"),
	_("Error"),
	_("Updating description failed."),
	_("Please try again!")
);



$translated_strings = array();

// Translate all array values using gettext
foreach($strings as $string) {

	$translated_strings[$string] = _($string);

}

echo json_encode($translated_strings);

?>
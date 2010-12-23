<?php
/* Hitchwiki Maps - language.php
 * Language
 * http://fi.php.net/manual/en/function.gettext.php
 * Requires:
 * - Config file loaded before
 * - Gettext
 */


// Set langauge from URL
if (isset($_GET["lang"])) {
    if (preg_match('!.._..!', $_GET['lang']))
        $settings['language'] = $_GET['lang'];
    else if (strlen($_GET['lang']) == 2) {
        $tlang = strtolower($_GET['lang']).'_'.strtoupper($_GET['lang']);

        if (array_key_exists($tlang, $settings["valid_languages"]))
            $settings["language"] = $tlang;
        else  {
            foreach($settings['valid_languages'] AS $short => $long) {
                if (substr($short, 0, 2) == $_GET['lang']) {
                    $settings['language'] = $short;
                    break;
                }
            }
        }
    }
}
// Set language from users settings
elseif(isset($user["language"]) && in_array($user["language"], $settings["valid_languages"])) {
	$settings["language"] = $user["language"];
}
// Set language from cookie
elseif(isset($_COOKIE[$settings["cookie_prefix"]."lang"]) && array_key_exists($_COOKIE[$settings["cookie_prefix"]."lang"], $settings["valid_languages"])) {
	$settings["language"] = $_COOKIE[$settings["cookie_prefix"]."lang"];
}
// Set language from preferred locale of the http agent
elseif(in_array(get_http_locale(), $settings["valid_languages"])) {
	$settings["language"] = get_http_locale();
}


// Set language to default and validate language
if(!isset($settings["language"]) OR !array_key_exists($settings["language"], $settings["valid_languages"])) {
	$settings["language"] = $settings["default_language"];
}

// Save / update language to cookie
if(isset($_COOKIE[$settings["cookie_prefix"]."lang"]) && $_COOKIE[$settings["cookie_prefix"]."lang"] != $settings["language"]) {
	setcookie($settings["cookie_prefix"]."lang", $settings["language"]);
}
elseif(!isset($_COOKIE[$settings["cookie_prefix"]."lang"]) || !array_key_exists($_COOKIE[$settings["cookie_prefix"]."lang"], $settings["valid_languages"])) {
	setcookie($settings["cookie_prefix"]."lang", $settings["language"]);
}


/*
 * Gettext
 * Gettext is looking translation from "./locale/LANGUAGE_CODE/LC_MESSAGES/maps.mo"
 * http://www.php.net/manual/en/function.gettext.php
 */


putenv('LC_ALL='.$settings["language"]);
setlocale(LC_ALL, $settings["language"]);

// Specify location of translation tables
bindtextdomain("maps", substr(realpath(dirname(__FILE__)), 0, -4)."/locale");
bind_textdomain_codeset("maps", 'UTF-8');

// Choose domain
textdomain("maps");

/*
 * Fix en -> en_UK
 * Not too nice way though. :-)
 */
function get_http_locale() {
	global $settings;

	foreach($settings["valid_languages"] as $code => $lang) {
		$replace_these[] = substr($code,0,2);
	}
	$replace_with = $settings["valid_languages"];

	return str_replace($replace_these, $replace_with, substr($_SERVER['HTTP_ACCEPT_LANGUAGE'], 0, 2));
}


?>

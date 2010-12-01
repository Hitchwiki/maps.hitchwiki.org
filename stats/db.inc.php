<?php

$config = readConfig('/etc/hitchwiki/hitchwiki.conf');

$db = mysql_connect($config['DB_HOST'], $config['DB_USERNAME'], $config['DB_PASSWORD']);

if (!$db) {
    echo "down for maintenance. Please try again later";
    die();
}

mysql_select_db('hitchwiki_maps');

$prefix = 't_';
$t_users = 'lh_view_users_mw_lh'; /* view to bb_user in lh-format */
$t_users_mw = 'lh_view_users_mw'; /* view to hitchwiki-usertable, in bb_user format */
$t_users_mw_nice = 'lh_view_users_mw_lh'; /* view to hitchwiki-usertable in lh-format */
$t_countries = $prefix.'countries';
$t_cities = 'geo_cities';
$t_points = $prefix.'points';
$t_ratings = $prefix.'ratings';
$t_types = $prefix.'types';
$t_trip = $prefix.'trip';

function tag($tag, $s) {
    return "<$tag>$s</$tag>";
}

function correctcase($name) {
    global $t_users_mw;
    $query = "SELECT user_login FROM $t_users_mw WHERE LOWER(user_login) = LOWER('$name') LIMIT 1";
    $res = mysql_query($query) or die (mysql_error());

    if (!mysql_num_rows($res))
        return $name;

    $row = mysql_fetch_row($res); 
    return $row[0];
}

function debug($s) {
    file_put_contents('/tmp/lh.dbg', date("[Y-m-d H:i:s] ").$s."\n", FILE_APPEND);
}

function getCountryCoords($c) {
    global $t_countries;
    $query = "SELECT lat, lng FROM $t_countries WHERE code='".mysql_escape_string($c)."'";
    $res = mysql_query($query) or die ($query."-".mysql_error());
    if ($r = mysql_fetch_row($res)) {
        return $r[0].", ".$r[1];
    } else {
        return "0, 0";
    }
}

function getCityCoords($c) {
    global $t_cities;
    $country = '';

    if (preg_match('!,!', $c)) {
        list($c, $country) = explode(',', $c);
    }
    $c = mysql_real_escape_string(trim($c));
    if (!empty($country))
        $country = getCountryCode(trim($country));

    if (empty($country))
        $countryquery = '';
    else
        $countryquery = "AND country = '$country'";

    $query = "SELECT lat, lng FROM $t_cities WHERE LOWER(city) = LOWER('$c') $countryquery";
    $res = mysql_query($query) or die ($query."-".mysql_error());

    if ($r = mysql_fetch_row($res))
        return $r[0].", ".$r[1];

    $query = "SELECT lat, lng, city FROM $t_cities WHERE (LOWER(city) LIKE LOWER('%$c%')) $countryquery";
    $res = mysql_query($query) or die ($query."-".mysql_error());

    if ($r = mysql_fetch_row($res))
        return $r[0].", ".$r[1];

    $query = "SELECT lat, lng, city FROM $t_cities WHERE (city SOUNDS LIKE '$c') $countryquery";
    $res = mysql_query($query) or die ($query."-".mysql_error());

    if ($r = mysql_fetch_row($res))
        return $r[0].", ".$r[1];

    $retval = "48.873663314036996, 2.2950804233551025";
    $last = '';
    while ($r = mysql_fetch_row($res)) {
        if (similar_text($last, $c) < similar_text($c, $r[2])) {
            $last = $r[2];
            $retval = $r[0].", ".$r[1];
        }
    }
    return $retval; 
}

function getCountryCode($country) {
    $f = file('countrycodes.txt');
    foreach ($f AS $l) {
        list($c, $code) = explode(';', trim($l));
        if (strtolower($country) == strtolower($c)) {
            return trim($code);
        }
    }
    return '';
}
function getCountryFromCode($inputcode) {
    $f = file('countrycodes.txt');
    foreach ($f AS $l) {
        list($c, $code) = explode(';', trim($l));
        if (strtolower($inputcode) == strtolower($code)) {
            $country = trim(ucwords(strtolower($c)));
            if (empty($country))
                return "$inputcode";
            return "$country";
        }
    }
    return 'unknown';
}

function getCountryZoom($c) {
    global $t_countries;
    $query = "SELECT zoom FROM $t_countries WHERE code='".mysql_escape_string($c)."'";
    $res = mysql_query($query);
    if ($r = mysql_fetch_row($res)) {
        return $r[0];
    } else {
        return "5";
    }
}

function setLanguage() {

    if (isset($_GET['locale'])) {
        $_SESSION['locale'] = $_GET['locale'];
    }


    // get locale
    if (!isset($_SESSION['locale'])) {
        $s = $_SERVER['HTTP_ACCEPT_LANGUAGE'];
        if (preg_match('/,/', $s)) {
            $l = strtolower(str_replace('-','_',substr($s, 0, strpos($s, ','))));
        } else {
            $l = strtolower(str_replace('-','_',$s)); 
        }
        list($lang, $country) = explode('_', $l);
        $_SESSION['locale'] = $lang;
    } else {
        $lang = $_SESSION['locale'];
    }

    $langs = array(
        'en' => 'en_EN',
        'de' => 'de_DE',
        'es' => 'es_ES',
        'fi' => 'fi_FI',
        'ru' => 'ru_RU',
        'fr' => 'fr_FR',
    );
    if (in_array($lang, array_keys($langs)))
        $locale = $langs[$lang];
    else
        $locale = 'en_EN';

    $domain = 'hitchwiki'; // setzt die Domäne
    $encoding = 'UTF-8'; // setzt die Zeichenkodierung
    setlocale(LC_ALL, $locale);

    bindtextdomain($domain, './languages');
    bind_textdomain_codeset($domain, $encoding);
    textdomain($domain);

}

function readConfig($path = '/etc/hitchwiki/hitchwiki.conf') {
	$conf = array();
	$f = file($path);
	foreach ($f AS $l) {
		list($key, $val) = explode('=', trim($l), 2); 
		$conf[$key] = $val;
	}   
	return $conf;
}


session_start();
setLanguage();

?>

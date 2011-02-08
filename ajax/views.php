<?php
/* Hitchwiki Maps - views.php
 * JS loads content from views-folder with this.
 *
 */ 

/*
 * Load config to set language
 */
require_once "../config.php";


/*
 * Returns an info-array about logged in user (or false if not logged in) 
 */
$user = current_user();


if($_GET["type"] == "card") $type = "cards";
elseif($_GET["type"] == "page") $type = "pages";
else  die(_("Error"));

$file = "../views/".$type."/".$_GET["page"].".php";


/*
 * Show page
 */
if( isset($_GET["page"]) && !empty($_GET["page"]) && file_exists($file) ): //!ereg('[^0-9A-Za-z_-]', $_GET["page"]) &&  (Function ereg() is deprecated)

	if($settings["debug"]==true) include($file);
	else @include($file);

/*
 * Not found error
 */
else:
	error_sign();
	echo '<h2>'._("Error 404 - page not found").'</h2><br /><br />';
	
	// For debugging:
	if($settings["debug"]==true) echo '<p><small>Page: '.htmlspecialchars($_GET["page"]).' | Type: '.$type.' | Lang: '.$settings["language"].'</small></p>';

endif;

?>
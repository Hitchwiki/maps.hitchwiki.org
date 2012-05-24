<?php
/* Hitchwiki Maps - views.php
 * JS loads content from views-folder with this.
 */ 

if(!isset($views_cold_include)) {
    require_once "../config.php"; //Load config to set language
    //$view_type = ($_GET["type"] == "card" ? 'cards' : 'pages');
    
    if($_GET["type"] == "card") $view_type = "card";
    elseif($_GET["type"] == "mobile") $view_type = "mobile";
    else $view_type = "pages";
    
    $views_path = "../";
}
else {
    $view_type = "pages";
    $views_path = "";
}

if($view_type == "cards") {
    $view_name = (isset($_GET["page"]) && !empty($_GET["page"]) && in_array($_GET["page"], $settings["views"][$view_type])) ? $_GET["page"]: "error404";
} else {
    $view_name = (isset($_GET["page"]) && !empty($_GET["page"]) && isset($settings["views"][$view_type][$_GET["page"]])) ? $_GET["page"]: "error404";
}

$view_file = $views_path."views/".$view_type."/".$view_name.".php";


/*
 * Show page
 */
if(file_exists($view_file)): //!ereg('[^0-9A-Za-z_-]', $_GET["page"]) &&  (Function ereg() is deprecated)

    if(!isset($views_cold_include)) $user = current_user(); // Returns an info-array about logged in user (or false if not logged in) 

	if($settings["debug"]==true) include($view_file);
	else @include($view_file);


/*
 * Not found -error
 */
else:
    include($views_path."views/view_404.php");
        
	// For debugging:
	if($settings["debug"]==true) echo '<p><small>Page: '.htmlspecialchars($_GET["page"]).' | Type: '.$view_type.' | Lang: '.$settings["language"].'</small></p>';

endif;

?>
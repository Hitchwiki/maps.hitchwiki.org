<?php

/*
 * Initialize Maps
 */
$settings["mobile"] = true;

if(@is_file('config.php')) require_once "config.php";
else { $settings["maintenance_page"] = true; $settings["non_maintenance_ip"] = array(); }


$settings["cache_buster"] = time();


/*
 * Put up a maintenance -sign
 * Set it up from config.php or test it from ./?maintenance
 */
if(isset($_GET["maintenance"])) $settings["maintenance_page"] = true;
if($settings["maintenance_page"]===true && !in_array($_SERVER['REMOTE_ADDR'], $settings["non_maintenance_ip"])) {

	include("maintenance_page.php");
	exit;

} // end of maintenance


/*
 * Map settings
 */

// Defaults
$zoom = '5';
$lat = '51';
$lon = '9';

$basehref = "../";



if(isset($_GET["place"]) && $_GET["place"] != "" && preg_match ("/^([0-9]+)$/", $_GET["place"])) {
	$place = get_place($_GET["place"], true);
	if($place["error"]!==true) {
		$show_place = htmlspecialchars($_GET["place"]);
	}
	else {
		$show_place_error = true;
		unset($place);
	}
}


/*
 * Set page
 */
switch ($_GET["page"]) {
    case "search":
        $page = "search";
        break;
    case "language":
        $page = "language";
        break;
    case "about":
        $page = "about";
        break;
    case "contact":
        $page = "contact";
        break;
    case "statistics":
        $page = "statistics";
        break;
    default:
       $page = "home";
}



/*
 *  Build a title, image, slogan and description
 */

// Title
// If place
if(isset($show_place) && !isset($show_place_error)) {
    $title .= _("a Hitchhiking spot in").' '; 

    // in city, country
    if(!empty($place["location"]["locality"])) $title .= $place["location"]["locality"].', ';

    $title .= $place["location"]["country"]["name"];
    $title .= ' - ';
}
if(isset($_GET["page"]) && !empty($_GET["page"]) && !empty($settings["views"]["pages"][$_GET["page"]]["title"])) {

    $title .= htmlspecialchars($settings["views"]["pages"][$_GET["page"]]["title"]);
    $title .= ' - ';
}
$title .= 'Hitchwiki '._("Maps");

// Image
if(isset($show_place) && !isset($show_place_error)) $website_img[] = image_map($place["lat"],$place["lon"]);
$website_img[] = $settings["base_url"].'/badge.png'; 

// Slogan
$slogan = _("Find good places for hitchhiking and add your own");

// Description
if(isset($show_place) && !isset($show_place_error) && !empty($place["description"]["en_UK"]["description"])) $description = htmlspecialchars(strip_tags($place["description"]["en_UK"]["description"]));	
else $description = $slogan;

// OG:URL
// OG:Type
if(isset($show_place) && !isset($show_place_error)) {
	/*
	if(!empty($place["location"]["locality"])): $og_type = "city";
	elseif(!empty($place["location"]["country"]["name"])): $og_type = "country";
	else */$og_type = "landmark";

	$og_url = $place["link"];
} else {
	$og_type = "website";
	$og_url = $settings["base_url"];
}





?><!DOCTYPE HTML>
<html lang="<?php echo langcode(); ?>">
<head>
	<meta charset="utf-8">
	<title><?php echo $title; ?></title>

	<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=0">
	<meta name="apple-mobile-web-app-capable" content="yes">

	<link rel="stylesheet" href="<?php echo $settings["base_url"]; ?>/static/jqtouch-themes/css/hitchwiki.css" title="jQTouch">
	<link rel="stylesheet" href="<?php echo $settings["base_url"]; ?>/static/css/main.mobile.css?c=<?php echo $settings["cache_buster"]; ?>" title="Hitchwiki Maps Mobile" />
	<?php
	
	/*
	 * Map Services
	 * You need to enable these from init_map() in static/js/main.mobile.js 
	 * Set API keys and such to the config.php
	 */
	
	// Google Maps API
	$settings["google"]["api"]["maps"]=false; // Fix this to false, we don't want googlemaps in mobile version now...
	 
	if($settings["google"]["api"]["maps"] == true) {
	    if($user["logged_in"]===true && empty($user["map_google"])) $print_map_google = false;
	    else $print_map_google = true;
	    
	    /* This is Maps API V3 script, wich doesn't need API key anymore. 
	     * It's already supported by OpenLayers, but there's annoying bug that stops us using it.
	     * While dragging map, overlay vectors follow with different speed.
	     * http://trac.osgeo.org/openlayers/ticket/2929
	     * http://openlayers.org/blog/2010/07/10/google-maps-v3-for-openlayers/
	     *
	     * Use V3 API by removing API key from the config file.
	     */
	    if($print_map_google && empty($settings["google"]["api"]["maps_api"])) {
	    	echo '<script src="http://maps.google.com/maps/api/js?v=3.2&&amp;sensor=true"></script>'."\n\t";
	    	echo '<script> var google_maps_api_v2 = false; </script>'."\n\t";
	    }
	    /* 
	     * Old Maps API v2 script:
	     * Remove from use when v3 works better.
	     */
	    elseif($print_map_google && !empty($settings["google"]["api"]["maps_api"])) {
	    	echo '<script src="http://maps.google.com/maps?file=api&amp;l='.shortlang().'&amp;v=2&amp;key='.$settings["google"]["api"]["maps_api"].'"></script>'."\n\t";
	    	echo '<script> var google_maps_api_v2 = true; </script>'."\n\t";
	    }
	}
	
	
	// Bing
	if(!empty($settings["bing"]["maps_api"])) {
	    if($user["logged_in"]===true && empty($user["map_bing"])) $print_map_bing = false;
	    else $print_map_bing = true;
	}
	
	// Nokia Ovi
	if($settings["ovi"]["maps"]===true) {
	    if($user["logged_in"]===true && empty($user["map_ovi"])) $print_map_ovi = false;
	    else $print_map_ovi = true;
	}
	
	
	?><script src="http://openlayers.org/dev/OpenLayers.mobile.js"></script>
	<script src="<?php echo $settings["base_url"]; ?>/ajax/js-translation.json.php?c=<?php echo $settings["cache_buster"]; ?>&amp;lang=<?php echo $settings["language"]; ?>" lang="<?php echo $settings["language"]; ?>" rel="gettext"></script>
	<!--<script src="<?php echo $settings["base_url"]; ?>/static/js/jquery.min.js?c=<?php echo $settings["cache_buster"]; ?>"></script>-->
	<script src="<?php echo $settings["base_url"]; ?>/static/js/zepto.min.js?c=<?php echo $settings["cache_buster"]; ?>" type="text/javascript" charset="utf-8"></script>
	<script src="<?php echo $settings["base_url"]; ?>/static/js/jqtouch.min.js?c=<?php echo $settings["cache_buster"]; ?>" type="text/javascript" charset="utf-8"></script>
	<script>
	    /*
	     * Misc settings
	     */
	    var ip = "<?php echo htmlspecialchars($_SERVER['REMOTE_ADDR']); ?>";
	    var geolocation = "ajax/geolocation_ip_proxy.php";
	    var cookie_prefix = "<?php echo $settings["cookie_prefix"]; ?>";
	    var geolocation_cookiename = "<?php echo $settings["cookie_prefix"]; ?>geolocation";
	    var geolocation_cookieoptions = { path: '/', expires: 6 }; // expires: hours
	    var locale = "<?php echo $settings["language"]; ?>";
	    var google_analytics = <?php echo (!empty($settings["google"]["analytics_id"]) ? 'true' : 'false'); ?>;
	    var piwik_analytics = <?php echo (!empty($settings["piwik"]["id"]) ? 'true' : 'false'); ?>;
	    var debug = <?php echo ($settings["debug"] == true) ? 'true' : 'false'; ?>;

	    /*
	     * Loaded Map layers
	     */
	    var layer_default = "<?php echo (isset($user["map_default_layer"]) && !empty($user["map_default_layer"])) ? htmlspecialchars($user["map_default_layer"]): 'mapnik'; ?>";
	    var layer_google = <?php echo ($settings["google"]["api"]["maps"]===true && $print_map_google===true) ? "true": "false"; ?>;
	    var layer_ovi  = <?php echo ($settings["ovi"]["maps"]===true && $print_map_ovi===true) ? "true": "false"; ?>;
	    var layer_bing = <?php echo (!empty($settings["bing"]["maps_api"]) && $print_map_bing===true) ? "true": "false"; ?>;
	    <?php if(!empty($settings["bing"]["maps_api"])) echo 'var layer_bing_key = "'.$settings["bing"]["maps_api"].'";'; ?>

	    /*
	     * Map settings
	     */
	    var lat = <?php echo $lat; ?>;
	    var lon = <?php echo $lon; ?>;
	    var layers = '<?php echo $layers; ?>';
	    var zoom = <?php echo $zoom; ?>;
	    var markersZoomLimit = 7; 

	    var basehref = '<?php echo $basehref; ?>';
	    var current_page = '<?php echo $page; ?>';
	
		<?php // Show welcome text after a maintenance break
		if(isset($_GET["post_maintenance"])): ?>
		
		    alert('<?php echo _("The maintenance break is now over").' - '. _('Sorry about that!').' '._('If something on the website seems wrong to you, please use "contact us" link at the bottom of the page.'); ?>');

		<?php endif; ?>

		<?php
		#$app_icons_and_screens = $settings["base_url"].'/static/gfx/mobile/app_icons-screens/';
		?>
	    /*
	     * Init jQTouch
	     */
		var jQT = new $.jQTouch({
		    /*
		    icon: 'jqtouch.png',
		    icon4: 'jqtouch4.png',
		    addGlossToIcon: false,
		    startupScreen: 'jqt_startup.png',
		    */
		    fullScreen: true,
		    statusBar: 'black-translucent',
		    //themeSelectionSelector: '#jqt #themes ul',
			cacheGetRequests: false,
		    preloadImages: []
		});
	</script>
	<script src="<?php echo $settings["base_url"]; ?>/static/js/main.mobile.js?c=<?php echo $settings["cache_buster"]; ?>"></script>

	<meta name="description" content="<?php echo $description; ?>" />

	<!-- The Open Graph Protocol - http://opengraphprotocol.org/ -->
	<meta property="og:title" content="<?php echo $title; ?>" />
	<meta property="og:site_name" content="Hitchwiki.org" />
	<meta property="og:description" content="<?php echo $description; ?>" />
	<meta property="og:url" content="<?php echo $og_url; ?>"/>
	<meta property="og:type" content="<?php echo $og_type; ?>" />
	<?php
    	/*
    	 * Language versions of the frontpage
    	 */ 
    	foreach($settings["valid_languages"] as $code => $name) {
    		echo '<meta property="og:locale';
    		
    		if($settings["language"] != $code) echo ':alternate';
    		
    		echo '" content="'.$code.'" />'."\n\t";
    		
    	}
    ?>
    <?php foreach($website_img as $img): ?><meta property="og:image" content="<?php echo $img; ?>" /><?php endforeach; ?>
<?php if(isset($place)): ?>
    <meta property="og:latitude" content="<?php echo $place["lat"]; ?>" />
    <meta property="og:longitude" content="<?php echo $place["lon"]; ?>" />
    <?php if(!empty($place["location"]["locality"])): ?><meta property="og:locality" content="<?php echo $place["location"]["locality"]; ?>" /><?php endif; ?>
    <?php if(!empty($place["location"]["country"]["name"])): ?><meta property="og:country-name" content="<?php echo $place["location"]["country"]["name"]; ?>" /><?php endif; ?>
    <meta name="geo.position" content="<?php echo $place["lat"].','.$place["lon"]; ?>" />
<?php endif; ?>

    <?php 
    	if(isset($settings["fb"]["admins"]) && !empty($settings["fb"]["admins"])) echo '<meta property="fb:admins" content="'.$settings["fb"]["admins"].'" />'."\n";
    	
    	if(isset($settings["fb"]["page_id"]) && !empty($settings["fb"]["page_id"])) echo '<meta property="fb:page_id" content="'.$settings["fb"]["page_id"].'" />'."\n";
    	
    	if(isset($settings["fb"]["app"]["id"]) && !empty($settings["fb"]["app"]["id"])) echo '<meta property="fb:app_id" content="'.$settings["fb"]["app"]["id"].'" />'."\n";
    ?>
    <link rel="search" type="application/opensearchdescription+xml" href="<?php echo $settings["base_url"]; ?>/opensearch/?lang=<?php echo $settings["language"]; ?>" title="Hitchwiki <?php echo _("Maps"); ?>" />

	<!--[if gte IE 9]>
	  <style type="text/css">
	    #jqt .toolbar,
	    #jqt ul li small.counter,
	    #jqt .button, #jqt .back, #jqt .cancel, #jqt .add
	    	{ filter: none; }
	  </style>
	<![endif]-->

	<?php 
		// Prints meta tags, icons and startup screens for mobile devices
		mobile_meta();

		// Google analytics
		init_google_analytics();
	?>
</head>
<body>

	<h1 class="ui-hidden-accessible"><?php echo $title; ?></h1>
	<p class="ui-hidden-accessible"><?php echo $description; ?></p>
	
	<div id="jqt">
	<?php
		#$ui_home_btn = '<a href="./?map#mappage" data-icon="arrow-l" data-direction="reverse" data-role="button" data-iconpos="notext">'._("Map").'</a>';
		#$ui_more_btn = '<a href="./#more" data-icon="arrow-l" data-direction="reverse" data-role="button" data-iconpos="notext">'._("Back").'</a>';
	
		include("views/mobile/".$page.".php");
	?>
	</div>

</body>
</html>
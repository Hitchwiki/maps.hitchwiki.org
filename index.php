<?php 
/*
 * Hitchwiki Maps: index.php
 * 2010
 *
 */
 
 
/*
 * Initialize Maps
 */
if(@is_file('config.php')) require_once "config.php";
else { $settings["non_maintenance_ip"] = array(); $settings["maintenance_page"] = true; }

/*
 * Put up a maintenance -sign
 * Set it up from config.php or test it from ./?maintenance
 */
if(isset($_GET["maintenance"])) { $settings["non_maintenance_ip"] = array(); $settings["maintenance_page"] = true; }
if($settings["maintenance_page"]===true && !in_array($_SERVER['REMOTE_ADDR'], $settings["non_maintenance_ip"])) { @include("maintenance_page.php"); exit; }



/*
 * Redirect to clean "rdfrom" set by mediawiki
 */
if(isset($_GET["rdfrom"])) {
	header("Location: ".$settings["base_url"]);
	exit;
}



/*
 * Returns an info-array about logged in user (or false if not logged in) 
 * With this we also check if user is logged in by every load
 * You should include this line to every .php where you need to know if user is logged in
 */
$user = current_user();



/*
 * Map settings
 */
// Zoom, lat, lon, layers
$zoom = (isset($_GET["zoom"]) && ctype_digit($_GET["zoom"])) ? $_GET["zoom"] : '4';

// Centered to Germany (51,9). Projection center would be '49','8.3'

$lat = (isset($_GET["lat"]) && is_numeric($_GET["lat"])) ? $_GET["lat"] : '51';
$lon = (isset($_GET["lon"]) && is_numeric($_GET["lon"])) ? $_GET["lon"] : '9';
#$layers = (isset($_GET["layers"]) && !empty($_GET["layers"])) ? strip_tags($_GET["layers"]) : 'B';
$layers = 'B';

if(!isset($_GET["lat"]) && !isset($_GET["lon"]) && !empty($user["country"])) {
	$countryinfo = country_info($user["country"]);
	if($countryinfo!==false) {
		$lat = $countryinfo["lat"];
		$lon = $countryinfo["lon"];
		if(!isset($_GET["zoom"])) $zoom = '5';
	}
}

// Markers visible -level
// Limit loading new markers only to this zoom level and deeper (bigger numbers = more zoom)
// Also hides markers-layer before this zoom level and show country places count -labels instead
$default_markersZoomLimit = '7';
$markersZoomLimit = (isset($_COOKIE[$settings["cookie_prefix"]."markersZoomLimit"]) && ctype_digit($_COOKIE[$settings["cookie_prefix"]."markersZoomLimit"])) ? $_COOKIE[$settings["cookie_prefix"]."markersZoomLimit"] : $default_markersZoomLimit;


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


?><!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Transitional//EN" "http://www.w3.org/TR/xhtml1/DTD/xhtml1-transitional.dtd">
<html 
	xmlns="http://www.w3.org/1999/xhtml" 
	xmlns:og="http://opengraphprotocol.org/schema/" 
	<?php 
	// Load schema only if FB-tags are filled in config
	if(!empty($settings["fb"])) echo 'xmlns:fb="http://developers.facebook.com/schema/"'."\n"; ?>
	dir="<?php echo langdir(); ?>" 
	lang="<?php echo langcode(); ?>">
	<head profile="http://gmpg.org/xfn/11">
		<meta http-equiv="Content-Type" content="text/html; charset=UTF-8" />
		<title><?php echo $title; ?></title>
		<link href="<?= $settings["base_url"]; ?>/static/css/ui-lightness/jquery-ui.css?c=<?php echo $settings["cache_buster"]; ?>" media="all" rel="stylesheet" type="text/css" />
		<?php

		/*
		 * Map Services
		 * You need to enable these from init_map() in static/js/main.js 
		 * Set API keys and such to the config.php
		 */

		 // Google Maps API
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
				echo '<script src="http://maps.google.com/maps/api/js?v=3.2&&amp;sensor=false" type="text/javascript"></script>'."\n\t\t";
				echo '<script type="text/javascript"> var google_maps_api_v2 = false; </script>'."\n\t\t";
			}
			/* 
			 * Old Maps API v2 script:
			 * Remove from use when v3 works better.
			 */
			elseif($print_map_google && !empty($settings["google"]["api"]["maps_api"])) {
				echo '<script src="http://maps.google.com/maps?file=api&amp;l='.shortlang().'&amp;v=2&amp;key='.$settings["google"]["api"]["maps_api"].'" type="text/javascript"></script>'."\n\t\t";
				echo '<script type="text/javascript"> var google_maps_api_v2 = true; </script>'."\n\t\t";
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

		?><script src="http://openlayers.org/api/OpenLayers.js" type="text/javascript"></script>
		<script src="<?php echo $settings["base_url"]; ?>/ajax/js-translation.json.php?c=<?php echo $settings["cache_buster"]; ?>&amp;lang=<?php echo $settings["language"]; ?>" lang="<?php echo $settings["language"]; ?>" rel="gettext"></script>
		<script type="text/javascript">
		//<![CDATA[

			/*
			 * Misc settings
			 */
			var ip = "<?php echo htmlspecialchars($_SERVER['REMOTE_ADDR']); ?>";
			var geolocation = "ajax/geolocation_ip_proxy.php";
			var cookie_prefix = "<?php echo $settings["cookie_prefix"]; ?>";
			var geolocation_cookiename = "<?php echo $settings["cookie_prefix"]; ?>geolocation";
			var geolocation_cookieoptions = { path: '/', expires: 6 }; // expires: hours
			var locale = "<?php echo $settings["language"]; ?>";
			var private_location = <?php echo (!empty($user["private_location"]) ? 'true' : 'false'); ?>;
			var google_analytics = <?php echo (!empty($settings["google"]["analytics_id"]) ? 'true' : 'false'); ?>;
			var piwik_analytics = <?php echo (!empty($settings["piwik"]["id"]) ? 'true' : 'false'); ?>;
			var geonames_username = <?php echo (!empty($settings["geonames"]["user"]) ? '"'.$settings["geonames"]["user"].'"' : 'false'); ?>;
			var show_log = <?php echo (isset($_GET["show_log"]) ? 'true' : 'false'); ?>;
			var open_page_at_start = <?php echo (isset($_GET["page"]) && !empty($_GET["page"]) ? 'true' : 'false'); ?>;
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
			var markersZoomLimit = <?php echo $markersZoomLimit; ?>; 

		//]]>
		</script>

		<script src="<?= $settings["base_url"]; ?>/static/js/jquery.min.js?c=<?php echo $settings["cache_buster"]; ?>" type="text/javascript"></script>
		<script src="<?= $settings["base_url"]; ?>/static/js/jquery-ui.min.js?c=<?php echo $settings["cache_buster"]; ?>" type="text/javascript"></script>
		<script src="<?= $settings["base_url"]; ?>/static/js/jquery.json-2.2.min.js" type="text/javascript"></script>
		<script src="<?= $settings["base_url"]; ?>/static/js/jquery.cookie.js" type="text/javascript"></script>
		<script src="<?= $settings["base_url"]; ?>/static/js/jquery.gettext.js" type="text/javascript"></script>
		<script src="<?= $settings["base_url"]; ?>/static/js/main.js?c=<?php echo ($settings["debug"] == true) ? time() : $settings["cache_buster"]; ?>" type="text/javascript"></script>

		<!-- Keep main stylesheet here after min.js/main.js -->
		<link rel="stylesheet" type="text/css" href="<?= $settings["base_url"]; ?>/static/css/main.css?c=<?php 
			if($settings["debug"]==true) echo time(); 
			else echo $settings["cache_buster"];
		?>" media="all" />
		
		<script type="text/javascript">
		//<![CDATA[
		<?php
        	/*
        	 * Open JS-pages requested by GET 'page'
        	 */
		?>
			$(document).ready(function() {

				<?php // Open page
				if(isset($_GET["page"]) && !empty($_GET["page"])): ?>

					open_page("<?php echo htmlspecialchars($_GET["page"]); ?>", false, true);

				<?php endif; ?>
				
				<?php // Open marker
				if(isset($show_place)): ?>

					showPlacePanel("<?php echo $show_place; ?>", true);

				<?php // Place asked, but didn't exist
				elseif(isset($show_place_error)): ?>

					info_dialog("<?php echo _("Sorry, but the place cannot be found.")."<br /><br />"._("The place you are looking for might have been removed or is temporarily unavailable."); ?>", "<?php echo _("The place cannot be found"); ?>", true);

				<?php endif; ?>
				
				<?php // Perform search
				if(isset($_GET["q"]) && !empty($_GET["q"])): ?>

					search("<?php echo htmlspecialchars(strip_tags($_GET["q"])); ?>");

				<?php endif; ?>
				
				<?php // Show welcome text after a maintenance break
				if(isset($_GET["post_maintenance"])): ?>
				
					info_dialog('<?php echo _('Sorry about that!').'<br /><br />'._('If something on the website seems wrong to you, please use "contact us" link at the bottom of the page.'); ?>', '<?php echo _("The maintenance break is now over"); ?>', false);

				<?php endif; ?>
				
			});
		//]]>
		</script>
		
		<?php mobile_meta(false); ?>
		
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
				
				echo '" content="'.$code.'" />'."\n\t\t";
				
			}
		?>
		<?php foreach($website_img as $img): ?><meta property="og:image" content="<?php echo $img; ?>" /><?php endforeach; ?>
	<?php /*<meta property="og:email" content="<?php echo $settings["email"]; ?>" /> */ ?>
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
		<link rel="home" href="<?php echo $settings["base_url"]; ?>/" title="Hitchwiki <?php echo _("Maps"); ?>" />
		<link rel="help" href="<?php echo $settings["base_url"]; ?>/about/" title="Hitchwiki <?php echo htmlspecialchars(_("Help & About")); ?>" />
		<link rel="search" type="application/opensearchdescription+xml" href="<?php echo $settings["base_url"]; ?>/opensearch/?lang=<?php echo $settings["language"]; ?>" title="Hitchwiki <?php echo _("Maps"); ?>" />
		<link rel="author" href="<?php echo $settings["base_url"]; ?>/humans.txt" type="text/plain" />
		<?php
		/*
		 * Language versions of the frontpage
		 */ 
		foreach($settings["valid_languages"] as $code => $name) {
			// Don't print current in-use-language page
			if($settings["language"] != $code) echo '<link type="text/html" rel="alternate" hreflang="'.shortlang($code).'" href="'.$settings["base_url"].'/?lang='.$code.'" title="'.$name.'" />'."\n\t";
		}
		?>
		
		<!--[if lt IE 7]>
		<style type="text/css"> .png, .icon { behavior: url(static/js/iepngfix.htc); } </style>
		<link rel="shortcut icon" href="<?php echo $settings["base_url"]; ?>/favicon.ico" type="image/x-icon" />
		<link rel="bookmark icon" href="<?php echo $settings["base_url"]; ?>/favicon.ico" type="image/x-icon" />
		<![endif]-->
		
	<?php 
		// Google analytics
		init_google_analytics();
	?>
    </head>
    <body class="<?php echo $settings["language"]." ".langdir(); ?>">
	<iframe src="http://hitchwiki.org/en/index.php?title=Maps.hitchwiki.org&amp;redirect=no&amp;action=render&amp;ctype=text/plain" frameborder="0" width="0" height="0" scrolling="no" style="display: block; width: 0; height: 0; border:0; position: absolute; top:-100px; left: -100px;" id="loginRefresh" name="loginRefresh"></iframe>
		<div id="Content">

		<div id="Header">
			<div id="Logo">
				<h1><a href="http://www.hitchwiki.org/"><span>Hitchwiki</span></a></h1>
				<h2><?php echo _("Maps"); ?></h2>
				<h3 class="hide-fix"><?php echo $slogan; ?></h3>

				<div class="HitchwikiPages">
					<a href="<?php echo _("http://hitchwiki.org/en/"); ?>"><?php echo _("Wiki"); ?></a>
					| <a href="http://hitchwiki.org/community/"><?php echo _("Community"); ?></a>
					<!--| <a href="http://hitchwiki.org/planet/"><?php echo _("Planet"); ?></a>-->
				</div>
					
				<div class="clear"></div>
				
				<ul id="Navigation" class="Navigation" role="navigation">
					<li><a href="#" id="add_place" class="icon add"><?php echo _("Add place"); ?></a></li>
					<li><a href="<?= $settings["base_url"]; ?>/countries/" id="countries" class="icon world pagelink"><?php echo _("Countries"); ?></a></li>
					<li><a href="<?= $settings["base_url"]; ?>/public_transport/" id="public_transport" class="icon pagelink underground"><?php echo _("Public transport"); ?></a></li>
				</ul>
				<ul id="Navigation2" class="Navigation" role="navigation"><?php
					$naviRefreshArea = true;
					require_once("ajax/header_navi.php");
				?></ul>
				
			<!-- /Logo -->
			</div>
			
			<div class="align_right">
					
					<div id="loginRefreshArea"></div>
					
					<div id="search">
					<form method="get" action="<?= $settings["base_url"]; ?>/" id="search_form" name="search" role="search">
						<div class="ui-widget">
						<input type="text" value="<?php if(isset($_GET["q"]) && !empty($_GET["q"])) echo htmlspecialchars(strip_tags($_GET["q"])); ?>" id="q" name="q" />
						<button type="submit" class="search_submit button" title="<?php echo _("Search"); ?>"> <span class="icon magnifier">&nbsp;</span><span class="hidden"><?php echo _("Search"); ?></span></button>
						<div class="clear"></div>
						</div>
					</form>
					</div>
					
					<div id="nearby" style="display:none;">
						<span class="locality" style="display:none;"><a href="#" title="<?php echo _("Show the city on the map"); ?>"></a></span>
						<!--<span class="country" style="display:none;"><a href="#" title="<?php echo _("Show the country on the map"); ?>"></a></span>-->
					</div>
					
			<!-- /Login -->
			</div>

		<!-- /Header -->
		</div>
		<div id="Login">
			<?php /* By submitting this with JS, you can reload this page and map will be as it was, if you fill lat/lon/zoom inputs and change post->get */ ?>
			<form method="post" action="<?= $settings["base_url"]; ?>/" id="reloadPage" class="hidden"><input type="submit" /></form>
		</div>

	        
	        <!-- Adding a alace panel -->
	       <div id="AddPlacePanel">
	       		<h4 class="icon add"><?php echo _("Add place"); ?></h4>
	       	</div>
	        <!-- /Adding a alace panel -->
	        
	        
			<!-- AJAX Content Area for pages-->
			<div id="pages">
				<a href="#close" class="close ui-button ui-corner-all ui-state-default ui-icon ui-icon-closethick" title="<?php echo _("Close"); ?>"><?php echo _("Close"); ?></a>
				<div class="page">
					<div class="content"><?php
						// Open page
						if(isset($_GET["page"]) && !empty($_GET["page"])) {
							$views_cold_include = true;
							require_once("ajax/views.php");
						}
					?> </div>
				</div>
			</div>
			<!-- /pages -->
	        
	        
			<!-- cards -->
			<div id="cards"></div>
			<!-- /pages -->
	        
	        
	        <!-- The Map -->
	        <div id="map">
	        	<br /><br />
	        	<?php echo _("Turn JavaScript on from your browser."); ?>
			</div>
	       <!-- /map -->
	       
	       
	        <!-- The Place panel -->
	       <div id="PlacePanel"></div>
	       <!-- /Place panel -->
	       
	       
	       <!-- Tools -->
	       <div id="toolsPanel" class="floatingPanel draggable hidden">
	       		<h4 class="icon lorry">
	       			<?php echo _("Tools"); ?>
	       			<a href="#close" class="close ui-icon ui-icon-closethick align_right" title="<?php echo _("Close"); ?>"><?php echo _("Close"); ?></a>
	       		</h4>
				<div class="controlToggle">
				
				        <span class="icon cursor">
				        	<input type="radio" name="type" value="none" id="noneToggle" onclick="toggleControl(this);" checked="checked" />
				        	<label for="noneToggle"><?php echo _("Navigate"); ?></label>
				        </span><br />
				        
				        <span class="icon vector">
                			<input type="radio" name="type" value="line" id="lineToggle" onclick="toggleControl(this);" />
                			<label for="lineToggle"><?php echo _("Measure distance"); ?></label>
				        </span><br />
				        
				        <span class="icon shape_handles">
				        	<input type="radio" name="type" value="polygon" id="polygonToggle" onclick="toggleControl(this);" />
				        	<label for="polygonToggle"><?php echo _("Measure area"); ?></label>
				        </span><br />
				        
				        <?php /* 
				        Note that the geometries drawn are planar geometries and the metrics returned by the measure control are planar 
				        measures by default. If your map is in a geographic projection or you have the appropriate projection definitions 
				        to transform your geometries into geographic coordinates, you can set the "geodesic" property of the control to 
				        true to calculate geodesic measures instead of planar measures.
				        
				        <input type="checkbox" name="geodesic" checked="checked" id="geodesicToggle" onclick="toggleGeodesic(this);" />
				        <label for="geodesicToggle"><?php echo _("Use geodesic measures"); ?></label>
				        */ ?>
				        
				    	<div class="align_right clear"><?php echo _("Measure"); ?>: <span id="toolOutput">-</span></div>
				    	
				    	<hr />
				    	
				    	<label class="icon zoom"><?php echo _("Show markers after zoom level"); ?>:</label>
				    	<div id="zoom_slider"></div>
				    	
				    	<span class="align_left"><?php echo _("Default"); ?>: <?php echo $default_markersZoomLimit; ?></span>
				    	<span class="align_right">
				    		<b id="zoom_slider_amount"></b><span id="zoomlevel">
				    											<span class="z_continent hidden"> - <?php echo _("Continent level"); ?></span>
				    											<span class="z_country hidden"> - <?php echo _("Country level"); ?></span>
				    											<span class="z_city hidden"> - <?php echo _("City level"); ?></span>
				    											<span class="z_streets hidden"> - <?php echo _("Street level"); ?></span>
				    										</span>
				    	</span>

				</div>
	       </div>
	       <!-- /tools -->
	       
	       
	       <!-- languages -->
	       <div id="languagePanel" class="floatingPanel hidden">
	       		<h4 class="icon world">
	       			<?php echo _("Choose language"); ?>
	       			<a href="#close" class="close ui-icon ui-icon-closethick align_right" title="<?php echo _("Close"); ?>"><?php echo _("Close"); ?></a>
	       		</h4>
				<div class="controlToggle">
				
				    <ul>
				    	<?php
				    	    // Print out available languages
				    	    foreach($settings["valid_languages"] as $code => $name) {
				    	    	?>
				    	    	<li>
				    	    		<span class="icon" style="background-image: url(<?= $settings["base_url"]; ?>/static/gfx/flags/<?php echo strtolower(shortlang($code, 'country')); ?>.png);">	
				    	    			<?php
				    	    			echo '<a href="'.$settings["base_url"].'/?lang='.$code.'"';
				    	    			if($code == $settings["language"]) echo ' class="selected"';
				    	    			echo ' title="'.$settings["languages_in_english"][$code].'">'.$name.'</a>';
				    	    			?>
				    	    		</span>
				    	    	</li>
				    	    	<?php
				    	    }
				    	?>
					</ul>
					<a href="<?= $settings["base_url"]; ?>/translate/" id="translate" class="pagelink"><small class="light"><?php echo _("Help us with translating!"); ?></small></a>
				    						        
				</div>
	       </div>
	       <!-- /languages -->
		

	       <!-- Placeholder for simple error/info -dialog. see info_dialog(); from main.js for more. -->
	       <div id="dialog-message"></div>
	       
	       
	       <!-- Loading -bar -->
	       <div id="loading-bar"><small class="title"></small></div>
	       

		<!-- Map selector -->
		<div id="map_selector">

			<div id="maplist" class="ui-corner-top">
				<ul>
					<li class="first">
						<h4 class="icon icon-osm">Open Street Map</h4>
						<ul class="map_options">
							
							<li><a href="#" name="mapnik"<?php
								if($user["map_default_layer"]=='mapnik' OR empty($user["map_default_layer"]) OR !isset($user["map_default_layer"])) {
									echo ' class="selected"';
									$selected_map_name = $map_layers["osm"]["mapnik"];
								} ?>><?php echo $map_layers["osm"]["mapnik"]; ?></a></li>
							
							<li><a href="#" name="osmarender"<?php
								if($user["map_default_layer"]=='osmarender') {
									echo ' class="selected"';
									$selected_map_name = $map_layers["osm"]["osmarender"];
								} ?>><?php echo $map_layers["osm"]["osmarender"]; ?></a></li>
						</ul>
					</li>
					
					<?php
					
					// Google
					if($settings["google"]["api"]["maps"]===true && $print_map_google===true) {
					?>
					<li>
						<h4 class="icon icon-google">Google</h4>
						<ul class="map_options">
						<?php
						foreach($map_layers["google"] as $map => $name) {
				    		echo '<li><a href="#google_'.$map.'" name="'.$map.'"';
				    		if($user["map_default_layer"]==$map) {
								echo ' class="selected"';
								$selected_map_name = $name;
							}
				    		echo '>'.$name.'</a></li>';
						}
						?>
						</ul>
					</li>
					<?php
					} //google
					
					// Bing
					if(!empty($settings["bing"]["maps_api"]) && $print_map_bing===true) {
					?>
					<li>
						<h4 class="icon icon-bing">Bing</h4>
						<ul class="map_options">
						<?php
						foreach($map_layers["bing"] as $map => $name) {
				    		echo '<li><a href="#bing_'.$map.'" name="'.$map.'"';
				    		if($user["map_default_layer"]==$map) {
								echo ' class="selected"';
								$selected_map_name = $name;
							}
				    		echo '>'.$name.'</a></li>';
						}
						?>
						</ul>
					</li>
					<?php
					} //bing
					
					// Nokia Ovi
					if($settings["ovi"]["maps"]===true && $print_map_ovi===true) {
					?>
					<li>
						<h4 class="icon icon-nokia_ovi">Nokia Ovi</h4>
						<ul class="map_options">
						<?php
						foreach($map_layers["ovi"] as $map => $name) {
				    		echo '<li><a href="#ovi_'.$map.'" name="'.$map.'"';
				    		if($user["map_default_layer"]==$map) {
								echo ' class="selected"';
								$selected_map_name = $name;
							}
				    		echo '>'.$name.'</a></li>';
						}
						?>
						</ul>
					</li>
					<?php
					} //ovi
					
				    ?>
				</ul>
			</div>
			<button id="selected_map" class="ui-corner-bottom"><?php echo _("Map"); ?>: <span class="map_name"><?php echo htmlspecialchars($selected_map_name); ?></span></button>
		</div>


	       
		<div id="Footer">
			<div class="content">

				<ul class="ToolsNavigation">
					<li><a href="#" id="download" class="icon page_white_put cardlink"><?php echo _("Download"); ?></a></li>
					<li><a href="#" id="link_here" class="icon link cardlink"><?php echo _("Link here"); ?></a></li>
					<li><a href="#" id="tools" class="icon lorry"><?php echo _("More tools"); ?></a></li>
				</ul>


				<ul class="MetaNavigation">
			    	<!--<li><a href="#" id="news" class="icon new pagelink"><?php echo _("News"); ?></a></li>-->
					<li><a href="#" id="toggleLanguages" title="<?php echo _("Choose language"); ?>">Language</a></li>
					<li><a href="<?= $settings["base_url"]; ?>/about/" class="pagelink" id="about"><?php echo htmlspecialchars(_("Help & About")); ?></a></li>
					<li><a href="<?= $settings["base_url"]; ?>/statistics/" class="pagelink" id="statistics"><?php echo _("Statistics"); ?></a></li>
					<li><a href="#" class="cardlink" id="contact"><?php echo _("Contact us!"); ?></a></li>
					<li><a href="<?= $settings["base_url"]; ?>/mobile/" class="pagelink" id="mobile"><?php echo _("Mobile"); ?></a></li>
			    	<li><a href="<?= $settings["base_url"]; ?>/about_api/" class="pagelink" id="api" title="<?php echo _("Developers"); ?>"><?php echo _("API"); ?></a></li>

			    	<?php // Visible only for admins
			    	if($user["admin"]===true): ?>
					    <?php if($settings["debug"] == true) { echo '<li><a href="#" class="toggle_log">'._("Toggle log").'</a></li>'; } ?>
			    		<li><a href="<?= $settings["base_url"]; ?>/admin/"><?php echo _("Admins"); ?></a></li>
					<?php endif; ?>
					<?php if(!isset($user["disallow_facebook"]) && $user["disallow_facebook"] != 1): ?><li><a href="http://www.facebook.com/Hitchwiki" class="icon facebook" title="Hitchwiki @ Facebook" style="float: left; padding: 0; margin: 0; width: 16px; height: 16px;"><span class="hidden">Hitchwiki @ Facebook</span></a></li><?php endif; ?>
					<li><a rel="license" href="<?php echo _("http://creativecommons.org/licenses/by-sa/3.0/"); ?>" title="<?php echo _("Licensed under a Creative Commons Attribution-ShareAlike 3.0 Unported License"); ?>"><img alt="<?php echo _("Creative Commons License"); ?>" src="static/gfx/cc-by-sa.png" width="48" height="15"/></a></li>
				</ul>
			</div>
		</div>
		
		
		<!-- /Content -->
		</div>
		
		<!-- for debugging -->
		<div id="log" class="hidden">
			<b class="handle">
				<?php echo _("Log"); ?>
	       		<a href="#close" class="close ui-icon ui-icon-closethick align_right" title="<?php echo _("Close"); ?>"><?php echo _("Close"); ?></a>
			</b>
			<ol><li>Hitchwiki Maps log started <?php echo date("r"); ?> on <?= $settings["base_url"]; ?>/</li></ol>
		</div>

<?php 

	// Load Facebook JS
	init_FB();

	// Piwik analytics
	init_piwik_analytics();

?></body></html>
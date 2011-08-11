<?php
/* Hitchwiki - maps
 * Functions to init scripts:
 * - Facebook
 * - Google analytics
 * - Piwik
 */


/*
 * Prints out Javascript to init Facebook
 * http://developers.facebook.com/docs/reference/javascript/
 */
function init_FB() {
	global $settings;
	
	if(isset($settings["fb"]["app"]["id"]) && !empty($settings["fb"]["app"]["id"])) {
	?>
	<div id="fb-root"></div>
	<script>
	  window.fbAsyncInit = function() {
	    FB.init({
			appId: '<?php echo $settings["fb"]["app"]["id"]; ?>', 
			status: true, 
			cookie: true,
			xfbml: true
		});
	  };
	  (function() {
	    var e = document.createElement('script'); e.async = true;
	    e.src = document.location.protocol +
	      '//connect.facebook.net/<?php
		      	
		      	// Localization + a little language fix
		      	if($settings["language"] == "en_UK") echo 'en_US';
		      	else echo $settings["language"]; 
		      	
		      ?>/all.js';
	    document.getElementById('fb-root').appendChild(e);
	  }());
	</script>
	<?php
	}
}

/*
 * Print out JS that renders XFBML elements on the page
 * - Requires loading of init_FB()
 * - You can pass element id or class to parse XFBML only inside it. Eg.: parse_XFBML('#element'); or parse_XFBML('.element');
 * - You can leave <script> wrapper out by setting $script_tags to 'false'.
 */
function parse_XFBML($element=false, $script_tags=true) {
	global $settings;
/*	
	echo '<div style="border:1px solid red;">';
	
	echo 'Loading parse_XFBML...';
	
	if($script_tags===true) echo ' started JS.<script type="text/javascript">';
	
	if(isset($settings["fb"]["app"]["id"]) && !empty($settings["fb"]["app"]["id"])) {

		echo 'FB.XFBML.parse(';
			
		if(!empty($element)) echo '$("'.strip_tags($element).'")';
			
		echo ');';
	
	}
	else echo 'maps_debug("Tried to parse XFBML, but no init_FB() loaded!");alert("error");';
	
	if($script_tags===true) echo '</script> ...ended it';
	
	
	echo '</div>';
*/
}



/*
 * Prints out Javascript to init Google Analytics
 * Insert this just before </head> tag
 * http://analytics.google.com
 */
function init_google_analytics() {
	global $settings;

	if(isset($settings["google"]["analytics_id"]) && !empty($settings["google"]["analytics_id"])) {
	?>
	<script type="text/javascript">
	
	  var _gaq = _gaq || [];
	  _gaq.push(['_setAccount', '<?php echo $settings["google_analytics_id"]; ?>']);
	  _gaq.push(['_trackPageview']);
	
	  (function() {
	    var ga = document.createElement('script'); ga.type = 'text/javascript'; ga.async = true;
	    ga.src = ('https:' == document.location.protocol ? 'https://ssl' : 'http://www') + '.google-analytics.com/ga.js';
	    var s = document.getElementsByTagName('script')[0]; s.parentNode.insertBefore(ga, s);
	  })();
	
	</script>
	<?php
	}
}


/*
 * Prints out Javascript to init Piwik analytics
 * http://piwik.guaka.org
 */
function init_piwik_analytics() {
	global $settings;


	if(isset($settings["piwik"]["id"]) && !empty($settings["piwik"]["id"])) {
	?>
	<!-- Piwik -->
	<script type="text/javascript">
	/* <![CDATA[ */
	var pkBaseURL = (("https:" == document.location.protocol) ? "https://piwik.guaka.org/" : "http://piwik.guaka.org/");
	document.write(unescape("%3Cscript src='" + pkBaseURL + "piwik.js' type='text/javascript'%3E%3C/script%3E"));
	/* ]]> */
	</script>
	<script type="text/javascript">
	/* <![CDATA[ */
	try {
	var piwikTracker = Piwik.getTracker(pkBaseURL + "piwik.php", <?php echo $settings["piwik_id"]; ?>);
	piwikTracker.setDocumentTitle("Hitchwiki Maps");
	piwikTracker.setDownloadClasses("download");
	piwikTracker.trackPageView();
	piwikTracker.enableLinkTracking();
	} catch( err ) {}
	/* ]]> */
	</script><noscript><img src="http://piwik.guaka.org/piwik.php?idsite=<?php echo $settings["piwik_id"]; ?>" style="border:0" alt=""/></noscript>
	<!-- /Piwik -->
	<?php
	}

}

?>
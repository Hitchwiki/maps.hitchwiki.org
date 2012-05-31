<h2><?php echo _("Hitchhikers guide to the galaxy"); ?></h2>
<h3 class="sub-title"><?php echo _("In your hands!"); ?></h3>

<div class="textbox">

	<div class="align_right" style="width: 190px; margin: 0 0 30px 30px;">

		<div id="screenshots" style="width: 190px; height: 338px; overflow: hidden;">
			<ul>
				<li><a href="<?= $settings["base_url"]; ?>/static/gfx/screenshot_nokia-2.jpg"><img src="<?= $settings["base_url"]; ?>/static/gfx/screenshot_nokia-2_small.jpg" width="190" height="338" alt="Hitchwiki Maps for Nokia" /></a></li>
				<li><a href="<?= $settings["base_url"]; ?>/static/gfx/screenshot_nokia-3.jpg"><img src="<?= $settings["base_url"]; ?>/static/gfx/screenshot_nokia-3_small.jpg" width="190" height="338" alt="Hitchwiki Maps for Nokia" /></a></li>
				<li><a href="<?= $settings["base_url"]; ?>/static/gfx/screenshot_nokia-4.jpg"><img src="<?= $settings["base_url"]; ?>/static/gfx/screenshot_nokia-4_small.jpg" width="190" height="338" alt="Hitchwiki Maps for Nokia" /></a></li>
			</ul>
		</div>
		<script type="text/javascript" src="<?= $settings["base_url"]; ?>/static/js/jquery.jcarousellite.min.js"></script>
		<script type="text/javascript">
		$(document).ready(function() {
			// Start screenshots -carousel
			$("#screenshots").jCarouselLite({
			    visible: 1,
			    auto: 3000,
			    speed: 400
			});
		});
		</script>
	
		<br /><br />

		<div class="textbubble smaller">
		<small>
				<strong><em><?php echo _("Are you a mobile developer?"); ?></em></strong> 
				<?php echo _("We would love to see Hitchwiki Maps in as many platforms as possible. We have an API to help you to do just that."); ?> 
				<a href="#" onclick="open_card('contact', '<?php echo _("Contact us!"); ?>'); return false;"><?php echo _("Contact us!"); ?></a> &bull; <a href="<?= $settings["base_url"]; ?>/about_api/" onclick="open_page('api'); return false;"><?php echo _("API"); ?></a> 
		</small>
		</div>
	
	</div>
	
	<?php
		printf(_("Get Hitchwiki Maps and its %s marked and rated spots with you when you're on the road!"), '<b>'.total_places().'</b>');
		echo " "._('Also a mobile version of <i>Hitchwiki</i> is available at <a href="http://m.hitchwiki.org">m.hitchwiki.org</a>');
	?><br />
	
	<h3><?php echo _("Get the app for free"); ?></h3>
	<a href="http://store.ovi.com/content/143209"><img src="<?= $settings["base_url"]; ?>/static/gfx/app_store_nokia.gif" title="Nokia Ovi Store" alt="Nokia Ovi Store" /></a>
	<!--<a href="#"><img src="<?= $settings["base_url"]; ?>/static/gfx/app_store_android.gif" alt="Android" /></a>-->
	
	<h3><?php echo _("Features"); ?></h3>
	<ul>
		<li><?php echo _("Can be used offline"); ?></li>
		<li><?php echo _("Preview each and every spot on the map")." <br /><small>("._("requires Internet connection such as wifi, 3G or other"); ?>)</small></li>
		<li><?php echo _("Search by location and distance"); ?></li>
		<li><?php echo _("See the rating and description of the spot"); ?></li>
		<li><?php echo _("Application is available in:")." "._("English").", "._("French").", "._("German")." "._("and")." "._("Lithuanian"); ?>.</li>
	</ul>

	<br />

	<small class="grey">
		<b><?php echo _("App should work on following phone models:"); ?></b><br />
		<b>S60 5th Edition:</b> Nokia 5250, Nokia C5-03, Nokia C6-00, Nokia 5233, Nokia 5530 XpressMusic, Nokia 5800 XpressMusic, Nokia N97, Nokia 5228, Nokia N97 mini, Nokia X6, Nokia 5230, <?php echo _("and"); ?> Nokia 5235.
		<b>Symbian^3:</b> Nokia C7-00, Nokia X7-00, Nokia N8-00, Nokia C6-01, Nokia C7 Astound, <?php echo _("and"); ?> Nokia E7-00.

		<br /><br />
		<?php echo _("Got suggestions or want to report a bug?").' Application by: <a href="http://mindomobile.com/">Mindo Mobile Solutions</a>'; ?>
	</small>


<div class="clear"></div>
</div><!-- /textblock -->



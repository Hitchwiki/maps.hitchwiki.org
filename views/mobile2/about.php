
	<!-- About -->
	<div data-role="page" id="about" data-title="Hitchwiki <?php echo _("Maps")." - "._("About"); ?>">
		<div data-role="header" data-theme="e" data-content-theme="c">
			<?= $ui_more_btn; ?>
			<h1><?php echo _("About"); ?></h1>
		</div>

	    <div data-role="content" data-theme="c">
	    
			<h3 style="text-align: center;"><?php echo _("Hitchhikers guide to the galaxy"); ?></h3>
			<h4 style="text-align: center;"><?php echo _("In your hands!"); ?></h4>

	        <div data-role="collapsible" data-collapsed="true" data-mini="true" data-theme="e" data-content-theme="c">
			    <h3><?php echo _("What is this?"); ?></h3>
				<p><?php echo _("This is supposed to be a worldmap for hitchhikers, showing good and bad hitching places. Feel free to add all your favourite hitching places (or even more) to the map."); ?></p>
			</div><!-- /collapsible -->
			
			<div data-role="collapsible" data-collapsed="true" data-mini="true" data-theme="e" data-content-theme="c">
			    <h3><?php echo _("How can I add places?"); ?></h3>
			    <p><?php echo _("Just click on <i>Add place</i> in the menu. Set the orange marker to the place and click on <i>Add place</i>. Make sure to zoom as close as possible, so the point will be more accurate. It is also helpful if you give your points a rating and maybe a little description (i.e. what kind of place this is or how to get there). Please write description at least in English."); ?></p>
			</div><!-- /collapsible -->
			
			
			<div data-role="collapsible" data-collapsed="true" data-mini="true" data-theme="e" data-content-theme="c">
			    <h3><?php echo _("Mobile apps"); ?></h3>
			    <p><?php printf(_('Native app for Nokia Symbian phones is available from <a href="%s" rel="external">Nokia Ovi Store</a>.'), 'http://store.ovi.com/content/143209'); ?></p>
			    <p><?php echo _('Also a mobile version of <i>Hitchwiki</i> is available at <a href="http://m.hitchwiki.org">m.hitchwiki.org</a>'); ?></p>
			</div><!-- /collapsible -->
			
			<div data-role="collapsible" data-collapsed="true" data-mini="true" data-theme="e" data-content-theme="c">
				<h3><?php echo _("People involved"); ?></h3>

				<ul>
					<li>Mikael Korpela</li>
					<li>MrTweek</li>
				</ul>
				
				<h4><?php echo _("Translators"); ?><br />
				<em><?php echo _("Thank you very much!"); ?></em></h4>
				<ul>
					<li><?php echo _("Chinese"); ?> &mdash; Mipplor</li>
					<li><?php echo _("Dutch"); ?> &mdash; Platschi</li>
					<li><?php echo _("English"); ?> &mdash; Mikael, Platschi</li>
					<li><?php echo _("Finnish"); ?> &mdash; Mikael</li>
					<li><?php echo _("French"); ?> &mdash; Perilisk</li>
					<li><?php echo _("German"); ?> &mdash; MrTweek, Platschi, Nils</li>
					<li><?php echo _("Hungarian"); ?> &mdash; pite, sipmester</li>
					<li><?php echo _("Italian"); ?> &mdash; Maurizio</li>
					<li><?php echo _("Lithuanian"); ?> &mdash; Mindo, Prino, Simona</li>
					<li><?php echo _("Polish"); ?> &mdash; Robert, Iza</li>
					<li><?php echo _("Portuguese"); ?> &mdash; Joao</li>
					<li><?php echo _("Romanian"); ?> &mdash; montaniard</li>
					<li><?php echo _("Russian"); ?> &mdash; Siberian explorer, Platschi, rAndoM</li>
					<li><?php echo _("Spanish"); ?> &mdash; Prino</li>
				</ul>
				
			</div><!-- /collapsible -->
	        
	        <br /><br />
	        
			<div class="ui-bar ui-bar-b">
				<a href="http://www.facebook.com/Hitchwiki" rel="external" data-role="button" data-mini="true"><?php printf(_('%s on Facebook'), 'Hitchwiki'); ?></a>
			</div>
			
			<?php /*
	        <p style="text-align: center;"><a href="http://www.facebook.com/Hitchwiki" rel="external" data-role="button" data-mini="true" data-inline="true" data-theme="b">Hitchwiki @ Facebook</a></p>
	        */ ?>
	        
	    </div><!-- /content -->

		<div data-role="footer" data-theme="e">
			<a href="./#more" data-icon="arrow-l" data-direction="reverse" data-role="button"><?php echo _("Back"); ?></a>
		</div>

	</div><!-- /page -->
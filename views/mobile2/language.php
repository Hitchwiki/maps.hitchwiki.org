
	<!-- contact -->
	<div data-role="page" id="language" data-title="Hitchwiki <?php echo _("Maps")." - "._("Language"); ?>">
	
		<div data-role="header" data-theme="e">
			<?= $ui_more_btn; ?>
			<h1><?php echo _("Choose language"); ?></h1>
		</div>
		
		<div data-role="content">
		
			<p>
			<ul data-role="listview" data-inset="true">
				<?php
				    // Print out available languages
				    foreach($settings["valid_languages"] as $code => $name) {
				
								if($code == $settings["language"]) echo '<li data-icon="check" class="checked">';
				    			else echo '<li data-icon="check">';
				    			
				    			
				    			echo '<a href="./?lang='.$code.'">';
				    			echo '<img src="'.$settings["base_url"].'/static/gfx/flags/'.strtolower(shortlang($code, 'country')).'.png" alt="" class="ui-li-icon">';
				    			echo $name;
				    			//'.$settings["languages_in_english"][$code].'
				    			echo '</a>';
				    			
				    			echo '</li>';
				
				    }
				?>
			</ul>
			</p>

		</div><!-- /content -->

	</div><!-- /page -->
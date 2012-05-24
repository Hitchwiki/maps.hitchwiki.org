
	<!-- contact -->
	<div data-role="page" id="contact" data-title="Hitchwiki <?php echo _("Maps")." - "._("Contact"); ?>">
			
		<div data-role="header" data-theme="e">
			<?= $ui_more_btn; ?>
			<h1><?php echo _("Contact"); ?></h1>
		</div>
		
		<div data-role="content">
			
			<?php
			
			// Handle form
			if(isset($_POST["message"])) {
			
				$ajax_include = true;
				require_once($basehref."ajax/contact.php");
				
				echo '<div data-theme="e" data-content-theme="c" class="ui-body ui-body-e ui-corner-all">';
				
				if($output["success"]) {
					echo '<h3>'._("Thank you very much!").'</h3>';
					echo '<p>'._("Your message was sent").'</p>';
				}
				else {
					echo '<h3>'._("Error").'</h3>';
					echo '<p>'._("Sending your message failed.")."<br /><br />"._("Please try again!").'</p>';
				}
				
				echo '</div>';
			}
			?>
			
			<p><?php printf(_("Drop us an email to %s or use this form"), '<a href="mailto:'.$settings["email"].'">'.$settings["email"].'</a>'); ?></p>

			<form id="contact_form" action="<?= $settings["mobile_url"]; ?>/?page=contact" method="post" class="ui-body ui-body-d ui-corner-all" data-transition="pop">
			<fieldset>
			<?php
				// Show user if registered, so they won't think they'd be sending it anonymously
				//$user = current_user();
				//if($user!==false) printf('<p>'._("From: %s").'</p>', $user["name"]);
			?>
				<input type="hidden" name="log" value="" />
				<input type="hidden" name="source" value="Mobile page" />
			
				<div data-role="fieldcontain">
					<label for="email"><?php echo _("Your email"); ?> <small>(<?php echo _("So we can reply to you"); ?>)</small></label>
					<input type="email" name="email" id="email" value="<?php
						if(!empty($user["email"])) echo $user["email"]; 
					?>" />
				</div>
				
				<div data-role="fieldcontain">
					<label for="message"><?php echo _("Message"); ?></label>
					<textarea name="message" id="message"></textarea>
				</div>
			
				<?php /*
				<input type="checkbox" value="true" id="usage_log" checked="checked" name="usage_log" /> <label for="usage_log"><?php echo _("Include an usage log"); ?> <small>(<a href="#" class="toggle_log"><?php echo _("Show"); ?></a>)</small></label>
			
				*/ ?>

				<button id="btn_send" type="submit" data-role="button" data-inline="true" data-theme="e"><?php echo _("Send"); ?></button>
			</fieldset>	    
			</form>
			

		</div><!-- /content -->

	</div><!-- /page -->
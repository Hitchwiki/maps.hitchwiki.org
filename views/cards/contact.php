
<h4><?php printf(_("Drop us an email to %s or use this form"), '<a href="'.$settings["email"].'">'.$settings["email"].'</a>'); ?></h4>

<form id="contact_form" action="#">
<?php
	// Show user if registered, so they won't think they'd be sending it anonymously
	$user = current_user();
	if($user!==false) printf('<p>'._("From: %s").'</p>', $user["name"]);
?>
	<label for="your_email"><?php echo _("Your email"); ?></label><br />
	<input type="text" name="your_email" id="your_email" size="25" maxlength="255" value="<?php
		if(!empty($user["email"])) echo $user["email"]; 
	?>" /><br />
	<small><?php echo _("So we can reply to you"); ?></small>

	<br /><br />

	<label for="message"><?php echo _("Message"); ?></label><br />
	<textarea name="message" id="message" rows="7"></textarea>

	<br /><br />

	<input type="checkbox" value="true" id="usage_log" checked="checked" name="usage_log" /> <label for="usage_log"><?php echo _("Include an usage log"); ?> <small>(<a href="#" class="toggle_log"><?php echo _("Show"); ?></a>)</small></label>

	<br /><br />

	<button id="btn_send" class="smaller" type="submit"><?php echo _("Send"); ?></button>
	<button id="btn_cancel" class="smaller"><?php echo _("Cancel"); ?></button>
				    
</form>

<script type="text/javascript">
	$(function() {

		// Create a toggle button for log
		$(".toggle_log").click(function(e){
		    e.preventDefault();
		    $("#log").toggle();
		});

		// Send
		$("#btn_send").button({
		    icons: {
		        primary: 'ui-icon-comment'
		    }
		});
		$("form#contact_form").submit(function(e) {
		    e.preventDefault();
		    maps_debug("Sending a contact form");

			show_loading_bar("<?php echo _("Loading..."); ?>");

			// Disable elements while sending
			$("#contact_form input, #contact_form textarea").attr('disabled', true);
			
			var post_email = $("input#your_email").val();
			var post_message = $("textarea#message").val();
			if($("#usage_log").is(":checked")) {
				var post_log = $("#log").html();
			} else {
				var post_log = '';
			}

			$.post('ajax/contact.php', { email: post_email, message: post_message, log: post_log }, 
			    function(data) {

			    	hide_loading_bar();

			    	if(data.success == true) {
			    		close_cards();
			    		info_dialog("<?php echo _("Thank you very much!"); ?>", "<?php echo _("Your message was sent"); ?>", true);
			    	}
			    	// Oops!
			    	else {
			    		info_dialog("<?php echo _("Sending your message failed.")."<br /><br />"._("Please try again!"); ?>", "<?php echo _("Error"); ?>", true);
			    		maps_debug("Contact form send failed. <br />- Error: "+data.error+"<br />- Data: "+data);
						$("#contact_form input, #contact_form textarea").removeAttr('disabled');
			    	}
			
			    }, "json"
			); // post end

		});


		// Cancel
		$("#btn_cancel").button({
		    icons: {
		        primary: 'ui-icon-cancel'
		    }
		}).click(function(e) {
		    e.preventDefault();
		    maps_debug("Cancel contacting...");
		    close_cards();
		});

			
	});
</script>

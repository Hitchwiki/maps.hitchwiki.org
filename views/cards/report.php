
<h4><?php echo _("Report a problem"); ?></h4>

<form>

	<b><?php echo _("Reference"); ?>: -</b>
	
	<br /><br />

	<label for="report_email"><?php echo _("Email"); ?></label><br />
	<input type="text" name="report_email" id="report_email" size="25" maxlength="255" />
	
	<br /><br />
	
	<label for="report_problem"><?php echo _("Describe the problem"); ?></label><br />
	<textarea name="report_problem" id="report_problem" rows="5"></textarea>
	
	<button id="btn_send" class="smaller"><?php echo _("Send"); ?></button>
	<button id="btn_cancel" class="smaller"><?php echo _("Cancel"); ?></button>
				    
</form>

<script type="text/javascript">
	$(function() {
	
		// Send
		$("#btn_send").button({
		    icons: {
		        primary: 'ui-icon-comment'
		    }
		}).click(function(e) {
		    e.preventDefault();
		    maps_debug("Reporting a problem");
		    alert("Not in use yet...");
		});
		
		
		// Cancel
		$("#btn_cancel").button({
		    icons: {
		        primary: 'ui-icon-cancel'
		    }
		}).click(function(e) {
		    e.preventDefault();
		    maps_debug("Cancel reporting a problem");
		});

			
	});
</script>

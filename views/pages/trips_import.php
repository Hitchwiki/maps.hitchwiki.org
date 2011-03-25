<?php

echo info_sign("This feature is under development and visible only for admins.",false);

?>


					<div style="width: 600px;">
				
					<h2>Import</h2>
								
					
					<label>Do you want to create a trip from imported markers?</label><br />
					<small class="note">Don't worry, you can adjust trips afterwards as you like.</small><br />
					<input type="radio" value="0" checked="checked" name="create_trip" id="create_trip_no" /> <label for="create_trip_no" class="checkbox">No, keep them seperate</label><br />
					<input type="radio" value="1" name="create_trip" id="create_trip_yes" /> <label for="create_trip_yes" class="checkbox">Yes, join markers</label>
					
					<div class="settings_sub_box" id="trip_settings" style="display: none;">
						<label for="trip_title">Give trip a name</label><br />
						<input type="text" class="bigger" size="40" maxlength="255" id="trip_title" />
					</div>
		
					<br /><br />
					
					<h4>Choose ways of import:</h4>
					
					
							<!-- on/off buttons -->
							<input type="checkbox" name="import_type_file" id="import_type_file" title="Toggle on/off" />
							<label class="bigger icon folder_database" style="margin-top: 3px; display: block; float:left;" for="import_type_file">Upload files</label>
							
							<div class="clear"><br /></div>
							
							<input type="checkbox" name="import_type_google_latitude" id="import_type_google_latitude" title="Toggle on/off" />
							<label class="bigger icon icon-google-latitude" style="margin-top: 3px; display: block; float:left;" for="import_type_google_latitude">Google Latitude</label>

							<div class="clear"><br /></div>
							
							<script type="text/javascript">
							/*
							$(function() {
								$("#import_type_file").onoff_toggle({
									onClickOff: function(){
										$(".import_option.files").slideUp();
									},
									onClickOn: function(){
										$(".import_option.files").slideDown();
									}
								});
								
								$("#import_type_google_latitude").onoff_toggle({
									onClickOff: function(){
										$(".import_option.files").slideUp();
									},
									onClickOn: function(){
										$(".import_option.files").slideDown();
									}
								});
							});
							*/
							</script>
							
							
					<div class="clear"></div>
					
					<ol class="import_options">
					
						<li class="import_option selected files">
							
							<ul class="filelist clean align_right" style="width: 300px; margin: 0 0 0 15px;">
								<li>
									<span class="filename">filename.kml &mdash; <i>13 places</i></span>
									<a href="#" class="remove_file align_right ui-icon ui-icon-circle-close ui-priority-secondary" title="Remove"></a>
								</li>
								<li>
									<span class="filename">filename.gpx &mdash; <i>1 place</i></span>
									<a href="#" class="remove_file align_right ui-icon ui-icon-circle-close ui-priority-secondary" title="Remove"></a>
								</li>
								<li>
									<div id="progressbar" style="height: 10px;"></div>
								</li>
							</ul>
							
							<label for="file">Choose a file to import</label><br />
							<input type="file" name="file" id="file" /><br />
							<small class="note">Supported formats are GPX and KML.<br />You can select more files after the first one.</small>
							
							<div class="clear"></div>
						</li>
						
						<li class="import_option google_latitude">

							<div style="width: 300px; height: 150px; background: #fff; float: right; margin: 0 0 0 15px;"></div>
						
						
							<div style="width: 245px; float: left;">
							
							<b>Google Latitude</b>
							<br />
							<input type="radio" name="glatitude_scale" id="glatitude_history_all" value="all" checked="checked" /> <label for="glatitude_history_all" class="checkbox">Import all un-imported history items</label><br />
							<input type="radio" name="glatitude_scale" id="glatitude_history_last" value="last" /> <label for="glatitude_history_last" class="checkbox">Import only my recent location</label><br />
							<input type="radio" name="glatitude_scale" id="glatitude_history_days" value="days" /> <label for="glatitude_history_days" class="checkbox">Import items between timerange:</label><br />
								
							<div class="settings_sub_box" id="glatitude_history_days_settings" style="display: none;">
								<label for="glatitude_history_days_from">From</label> <input type="text" value="" size="10" maxlength="6" name="glatitude_history_days_from" /><br />
								<label for="glatitude_history_days_to">To</label> <input type="text" value="20.3.2011" size="10" maxlength="6" name="glatitude_history_days_to" />
							</div>
								
							</div>						
		
							<!--
							<iframe src="http://www.google.com/latitude/apps/badge/api?user=8536713835748043793&type=iframe&maptype=roadmap" width="100%" height="200" frameborder="0"/>	
							-->
							
							
							<div class="clear"></div>
						</li>
						
						
					</ol>
					<div class="clear"></div>
					
					<div class="ui-state-highlight ui-corner-all" style="padding: 0 .7em; margin: 20px 0;" id="info_123"> 
		    		<p><span class="ui-icon ui-icon-info" style="float: left; margin-right: .3em;"></span>  
		    		<span class="info_text">You will see all the places about to be imported and edit them before saving.</span></p>
		    		</div>
		    
						    		
					<!-- save/update -->
					<button id="btn_import" class="align_right">Continue</button>
					
					<!-- cancel -->
					<button id="btn_import_cancel" class="ui-priority-secondary align_right">Cancel</button>
	
						<div class="clear"></div>
					</div>
					
					<!--
					<div class="or"><span>and</span></div>
					-->
					
<script type="text/javascript">
$(function() {

		
	// Toggle more settings specific to Google Latitude dayrange
    $("input[name='glatitude_scale']").change(function() {
		if($(this).attr("checked") && $(this).val() == "days" && $("#glatitude_history_days_settings").is(":hidden")) {
			$("#glatitude_history_days_settings").slideDown("fast");
		} 
		else if($("#glatitude_history_days_settings").is(":visible")) {
			$("#glatitude_history_days_settings").slideUp("fast");
		} 
	});
		

	// Toggle more settings specific to Google Latitude
    $("input[name='create_trip']").change(function() {
		if($(this).val() == "1" && $("#trip_settings").is(":hidden")) {
			$("#trip_settings").slideDown("fast");
		} 
		else if($("#trip_settings").is(":visible")) {
			$("#trip_settings").slideUp("fast");
		} 
	});
	
	$("#progressbar").progressbar({
			value: 37
	});
	

	// Continue
    $("#btn_import").button({
        icons: {
            secondary: 'ui-icon-arrowthick-1-e'
        }
    }).click(function(e) {
    	e.preventDefault();
    	
    	
    });
    
    
	// Cancel
    $("#btn_import_cancel").button({
        icons: {
            primary: 'ui-icon-cancel'
        }
    }).click(function(e) {
    	e.preventDefault();
    	maps_debug("Cancel: Importing");
    	close_page();
    });
	
	
});
</script>
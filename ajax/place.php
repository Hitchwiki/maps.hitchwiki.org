<?php
/*
 * Hitchwiki Maps: place.php
 * Show a place panel
 */

/*
 * Load config to set language and stuff
 */
require_once "../config.php";

start_sql();

/* 
 * Gather data
 */
if(isset($_GET["id"]) && is_numeric($_GET["id"])) {

	$place = get_place($_GET["id"],true);

}
else {
	echo '<p>'._("Sorry, but the place cannot be found.<br /><br />The place you are looking for might have been removed or is temporarily unavailable.").'</p>';
	exit;
}


/*
 * Returns an info-array about logged in user (or false if not logged in) 
 */
$user = current_user();


/* 
 * Print stuff out in HTML:
 */

if($place["error"] !== true):
?>


<ul id="Navigation" id="place">

	<!-- title -->
    <li style="background: #fff;">

		<ul>
			<li>
				<h3 style="display: inline;"><?php echo _("Hitchhiking spot"); ?></h3>
				<div class="align_right">
					
					<a href="#" class="closePlacePanel ui-button ui-corner-all ui-state-default ui-icon ui-icon-closethick align_right" title="<?php echo _("Close"); ?>"></a>
					 
					<a class="icon icon_right zoom_in align_right" style="margin-right: 5px; background-position: center 1px;" href="#" title="<?php echo _("Zoom in"); ?>">&nbsp;</a>
					
					<script type="text/javascript">
					    $(function() {
					    
					    	// Zoom in
					    	$(".zoom_in").click(function(e) {
					    		e.preventDefault();
					    		$(this).blur();
					    		zoomMapIn(<?php echo $place["lat"]; ?>, <?php echo $place["lon"]; ?>, 16);
					    	});
					    
					    	// Close
					    	$(".closePlacePanel").click(function(e) {
					    		e.preventDefault();
					    		maps_debug("Asked to close place panel from [x]");
					    		hidePlacePanel();
					    		$('#map').click();
					    	});
					    });
					</script>
				</div>
			</li>
		</ul>
	</li>


	<!-- name, description & rating -->
	<li>
		<ul>
			<li>
				<h3 style="display: inline;"><?php
				
					// Flag
					if(!empty($place["location"]["country"]["iso"])) echo '<img class="flag" alt="'.$place["location"]["country"]["iso"].'" src="static/gfx/flags/'.strtolower($place["location"]["country"]["iso"]).'.png" /> ';
					
					// Town/City
					if(!empty($place["location"]["locality"])) echo $place["location"]["locality"].", ";
					
					// Country
					if(!empty($place["location"]["country"]["name"])) echo $place["location"]["country"]["name"];
					
					// Continent
					#if(!empty($place["location"]["continent"]["name"])) echo $place["location"]["continent"]["name"]."<br />";
					
				?></h3>
			</li>
				
				
			<?php if(!empty($place["description"])): ?>
			<li>
				
				<!-- description in different languages -->
				<label for="select_description"><?php echo _("Description"); ?></label> <select name="select_description" id="select_description">
				    <?php
				    // Print out lang options
				    
				    $selected_tab = $settings["default_language"];
				    foreach($settings["valid_languages"] as $code => $name) {
				    
				        if($code == $settings["language"] && !empty($place["description"][$code])) $selected_tab = $code;
				        
				        echo '<option value="'.$code.'">';
				        
				        if(!empty($place["description"][$code])) echo '&bull; ';
				        else echo '&nbsp;&nbsp;';
				        
				        echo $name;	        
				        echo '</option>';
				        $i++;
				    }
				    ?>
				</select>
				<div id="descriptions">
				    <?php
				    // Print out lang textareas
				    foreach($settings["valid_languages"] as $code => $name) {
				        echo '<div id="tab-'.$code.'" class="description">';
				    	echo '<p>';
				    	
				    	if(!empty($place["description"][$code])) {
				    		
				    		$allow_editing = false;
				    		
				    		// Edit link, only for registered users
				    		if($user!==false && $allow_editing == true) echo '<a href="#" class="edit_description" id="description_'.$code.'" lang="'.langcode($code).'" title="'._("Edit").'">';

				    		echo Markdown($place["description"][$code]["description"]);
				    		//'.langcode($code).'
				    		if($user!==false && $allow_editing == true) {
				    			echo '</a><div class="edit_description_editing" id="edit_description_editing_'.langcode($code).'" style="display: none;" lang="'.langcode($code).'">';
				    			echo '<textarea rows="5" lang="'.langcode($code).'">'.htmlspecialchars($place["description"][$code]["description"]).'</textarea><br />';
				    			echo '<input type="hidden" name="original_description" class="original_description" lang="'.langcode($code).'" value="'.htmlspecialchars($place["description"][$code]["description"]).'" />';
				    			echo '<small>';
				    				echo '<b><a href="#'.langcode($code).'" class="save">'._("Save").'</a></b> - ';
				    				echo '<a href="#'.langcode($code).'" class="recover">'._("Undo changes").'</a> - ';
				    				echo '<a href="#'.langcode($code).'" class="cancel">'._("Cancel").'</a>';
				    			echo '</small></div>'; 
				    		}

				    		// Date 
							if(!empty($place["description"][$code]["datetime"])) {
							    echo '<br /><small title="'.date(DATE_RFC822,strtotime($place["description"][$code]["datetime"])).'">';
								$description_date = date("j.n.Y",strtotime($place["description"][$code]["datetime"]));
							    
							    if($place["description"][$code]["versions"] > 1) {
							    	printf(_('Description edited %s'), $description_date);
							    	echo ' &mdash; <a href="#" onclick="place_history('.$place["id"].', \''.langcode($code).'\'); return false;">'._("History").'</a>';
							    }
							    else {
							    	printf(_('Description written %s'), $description_date);
							    }
							    echo '</small>';
							}
							?>

				    		<div class="clear"></div>

				    		<?php
				    	} else {
				    		// Editing box (only for registered users):
				    		
				    		if($user!==false) {
				    		?>
				    		<textarea rows="4" style="margin-bottom: 5px;" id="add_description_<?php echo $code; ?>"></textarea>
				    		<br />
				    		<small style="display:block; width: 143px; float: left;"><em><?php echo _("No description available for this language."); ?> <?php echo _("Write one?"); ?></em></small>
				    		<button id="btn_save_description_<?php echo $code; ?>" class="align_right smaller"><?php echo _("Save"); ?></button>
				    		<div class="clear"></div>
							<script type="text/javascript">
							$(function() {
							
				    			$("#btn_save_description_<?php echo $code; ?>").button({
				    			    icons: {
				    			        primary: 'ui-icon-pencil'
				    			    }
				    			}).click(function(e) {
				    				e.preventDefault();
				    				// Save written description
				    				maps_debug("(button) Save a description for <?php echo $code; ?>");
				    				saveDescription('<?php echo $place["id"]; ?>', '<?php echo $code; ?>', $("#add_description_<?php echo $code; ?>").val());
				    			});
							
							});
							</script>
				    		<?php
				    		} else {
				    			echo '<em>'._("No description available for this language.").'</em>';
				    			echo '<br /><br />';
				    			printf('<small>'._('You need to be <a href="%s">logged in</a> to add or edit descriptions.').'</small>', 'http://hitchwiki.org/en/index.php?title=Special:UserLogin&returnto=Maps.hitchwiki.org');
				    		}
				        }
				        
				        echo '</p></div>';
				    }
				    ?>
				</div>
				
				<script type="text/javascript">
				$(function() {
				
					// Descreption language selection
				    $("#descriptions .description").hide();
				    $("#descriptions #tab-<?php echo $selected_tab; ?>").show();
				    
				    $("#select_description").change( function () { 
				    	var selected_language = $(this).val();
				    	$(this).blur();
				    	$("#descriptions .description").hide();
				    	$("#descriptions #tab-"+selected_language).show();
						stats("read_description/"+selected_language);
				    });
				    
					
				});
				
			<?php 
			// Editing only for logged in users
			if($user!==false && $allow_editing == true): ?>
			    $("a.edit_description").click(function(e){
			    	e.preventDefault();
			    	
			    	var edit_lang_id = $(this).attr("lang");
			    	var edit_lang = edit_lang_id.replace('-','_');
			    	
			    	maps_debug("Editing description for "+edit_lang_id);
			    	
			    	var editing_area = $('.edit_description_editing[lang='+edit_lang_id+']');
			    	editing_area.show();
			    	$(this).hide();
			    });
			    
			    $(".edit_description_editing .recover").click(function(e){
			    	e.preventDefault();
			    	var edit_lang_id = $(this).attr("href").replace("#", "");
			    	maps_debug("Recover original description for "+edit_lang_id);
			    	
			    	var original_text = $('.original_description[lang='+edit_lang_id+']').val();
			    	$('.edit_description_editing[lang='+edit_lang_id+'] textarea').val(original_text);
			    	maps_debug("Text for "+edit_lang_id+" replaced with original: "+original_text);
			    	
			    });
			    
			    $(".edit_description_editing .cancel").click(function(e){
			    	e.preventDefault();
			    	var edit_lang_id = $(this).attr("href").replace("#", "");
			    	maps_debug("Cancel editing for "+edit_lang_id);
			    	
			    	// Recover original text first
			    	var original_text = $('.original_description[lang='+edit_lang_id+']').val();
			    	$('.edit_description_editing[lang='+edit_lang_id+'] textarea').val(original_text);
			    	maps_debug("Text for "+edit_lang_id+" replaced with original: "+original_text);
			    	
			    	$('.edit_description_editing[lang='+edit_lang_id+']').hide();
			    	$('.edit_description[lang='+edit_lang_id+']').show();
			    	
			    });
			    
			    $(".edit_description_editing .save").click(function(e){
			    	e.preventDefault();
			    	var edit_lang_id = $(this).attr("href").replace("#", "");
			    	var edit_lang = edit_lang_id.replace('-','_');
			    	maps_debug("Save edit for "+edit_lang_id);
			    	
			    	var new_text = $('.edit_description_editing[lang='+edit_lang_id+'] textarea').val();
			    	maps_debug("New text for "+edit_lang_id+": " +new_text);
			    	/*
			    	$('.edit_description_editing[lang='+edit_lang_id+']').hide();
			    	$('.edit_description[lang='+edit_lang_id+']').show();
			    	*/
			    	
				    saveDescription('<?php echo $place["id"]; ?>', edit_lang, $('.edit_description_editing[lang='+edit_lang_id+'] textarea').val());
			    	
			    });
			    
			<?php endif; ?>
				
				</script>
			</li>
			<?php endif; /* end if empty description */ ?>
			
		</ul>
	</li>
	<li>
		<ul>
			
			<li>

				<!-- Hitchability -->
				<?php 
					echo '<b>'._("Hitchability").':</b> '.hitchability2textual($place["rating"]).' <b class="bigger hitchability_color_'.$place["rating"].'">&bull;</b> ';
					echo '<small class="light">('.sprintf(ngettext("%d vote", "%d votes", $place["rating_stats"]["rating_count"]), $place["rating_stats"]["rating_count"]).')</small>';
				?>
				
				<?php if($place["rating_stats"]["rating_count"] > 1): ?>
					<br /><small class="light"><?php echo _("Vote distribution"); ?>:</small><br />
					<!--<img src="<?php echo rating_chart($place["rating_stats"], 220); ?>" alt="<?php echo _("Vote distribution"); ?>" />-->
					<?php echo rating_chart_html($place["rating_stats"]); ?>
				<?php endif; ?>
				
			
			<?php
			
			// Check if user has already rated this point, and if, what did one rate?
			$users_rating = false;
			if($user["logged_in"]===true) {
			
				$res4 = mysql_query("SELECT `fk_user`,`fk_point`,`datetime`,`rating` FROM `t_ratings` WHERE `fk_user` = ".mysql_real_escape_string($user["id"])." AND `fk_point` = ".mysql_real_escape_string($place["id"])." LIMIT 1");
   				if(!$res4) return $this->API_error("Query failed! (4)");
				
				// If we have a result
				if(mysql_num_rows($res4) > 0) {
					// Get an ID of row we need to just update
					while($r = mysql_fetch_array($res4, MYSQL_ASSOC)) {
						$users_rating = $r["rating"];
						$users_rating_date = $r["datetime"];
					}
				}
				
			}
			
			?>
				<br />
				<select name="rate" id="rate" class="smaller">
					<?php if($users_rating==false): ?><option value=""><?php echo _("Your opinion..."); ?></option><?php endif; ?>
					<option value="1"<?php if($users_rating==1) echo ' selected="selected"'; ?>><?php echo hitchability2textual(1); ?></option>
					<option value="2"<?php if($users_rating==2) echo ' selected="selected"'; ?>><?php echo hitchability2textual(2); ?></option>
					<option value="3"<?php if($users_rating==3) echo ' selected="selected"'; ?>><?php echo hitchability2textual(3); ?></option>
					<option value="4"<?php if($users_rating==4) echo ' selected="selected"'; ?>><?php echo hitchability2textual(4); ?></option>
					<option value="5"<?php if($users_rating==5) echo ' selected="selected"'; ?>><?php echo hitchability2textual(5); ?></option>
					<?php /* if($user["logged_in"]===true): ?><option value="clear"><?php echo _("Clear my rating"); ?></option><?php/ endif;  TODO! */ ?>
				</select>
				<?php
				
				if(!empty($users_rating_date)) echo '<br /><small class="light">'._("You rated for this place").' <span title="'.date(DATE_RFC822, strtotime($users_rating_date)).'">'.date("j.n.Y", strtotime($users_rating_date)).'</span></small>';
				
				?>
				<script type="text/javascript">
					$(function() {
					
						// Rate a place
				    	$("#rate").change( function () { 
				    	
				    		var rate = $(this).val();
				    		$(this).blur();
				    	
				    		if(rate != "") {
				    			maps_debug("Rating a place with "+rate);
				    			
				    			// Send an api call
								var apiCall = "api/?rate="+rate+"&place_id=<?php 
								
									echo $place["id"]; 
								
									if($user["logged_in"]===true) echo '&user_id='.$user["id"];
								
								?>";
								maps_debug("Calling API: "+apiCall);
								$.getJSON(apiCall, function(data) {
									
									if(data.success == true) {
										maps_debug("Rating saved. Place "+data.point_id+" rating: "+data.rating_stats.exact_rating);
										showPlacePanel(<?php echo $place["id"]; ?>);
									}
									// Oops!
									else {
									    info_dialog("<?php echo _("Rating failed, please try again."); ?>", "<?php echo _("Rating failed"); ?>", true);
									    maps_debug("Rating failed. <br />- Error: "+data.error+"<br />- Data: "+data);
									    $("#rate").val("");
									}
									
								});
								
				    		}
				    				    	
				    	});
				    });
				</script>
				
			</li>
		</ul>
	</li>
	<li>
		<ul>
			<li>
				<!-- Waiting time -->
				<?php 
				
				echo '<b title="'._("Average").'">'._("Waiting time").':</b> ';
				
				if($place["waiting_stats"]["count"] > 0) {
					echo $place["waiting_stats"]["avg_textual"].' <small class="light">(<a href="#" id="show_waitingtime_log" title="'._("Show log").'">'; 
					printf(ngettext("%d experience", "%d experiences", $place["waiting_stats"]["count"]), $place["waiting_stats"]["count"]);
					echo '</a>)</small>';
				}
				else echo _("Unknown");
				?>
				
				<br />
				
				<span class="waitingtime_free smaller hidden">
					<input type="text" value="" name="waitingtime_hours" id="waitingtime_hours" size="2" maxlength="2" class="smaller" style="text-align:right;" /> <label for="waitingtime_hours"><?php echo _("hours"); ?></label>&nbsp; 
					<input type="text" value="" name="waitingtime_minutes" id="waitingtime_minutes" size="3" maxlength="3" class="smaller" style="text-align:right;" /> <label for="waitingtime_minutes"><?php echo _("minutes"); ?></label> 
				</span>
				
				<select name="waitingtime" id="waitingtime" class="waitingtime_easy smaller">
					<option value=""><?php echo _("Your experience..."); ?></option>
					<option value="5"><?php echo nicetime(5); ?></option>
					<option value="10"><?php echo nicetime(10); ?></option>
					<option value="15"><?php echo nicetime(15); ?></option>
					<option value="20"><?php echo nicetime(20); ?></option>
					<option value="30"><?php echo nicetime(30); ?></option>
					<option value="45"><?php echo nicetime(45); ?></option>
					<option value="60"><?php echo nicetime(60); ?></option>
					<option value="other"><?php echo _("Other..."); ?></option>
				</select>&nbsp;
				<a href="#" id="waitingtime_add" class="ui-button ui-corner-all ui-state-default ui-icon ui-icon-plus"><?php echo _("Add"); ?></a>
				
				<div id="waitingtime_log"></div>
				
				<!--<button id="waitingtime_add" class="button smaller"><?php echo _("Add"); ?></button>-->
				<script type="text/javascript">
					$(function() {
					
						/* 
						 * Save timing
						 */
						 
						// Regognice "other" selection of the waitingtime
				    	$("select#waitingtime").change( function () { 
				    		if($(this).val()=="other") {
				    			$(this).hide();
				    			$(".waitingtime_free").show();
				    			maps_debug("Use free inputs for waitingtime instead.");
				    		}				    		
				    	});
				    
				    	// Add -button
				    	$("a#waitingtime_add").click(function(e){ 
				    		e.preventDefault();
							
							// Are we getting timing from free-inputs or from the select-input?
							if($(".waitingtime_free").is(":visible")) {
								
								maps_debug("Getting timing from free timing inputs.");
							
								var waitingtime_hours = $(".waitingtime_free input#waitingtime_hours").val();
								var waitingtime_minutes = $(".waitingtime_free input#waitingtime_minutes").val();
								
								if(waitingtime_hours=="") { waitingtime_hours = '0'; }
								if(waitingtime_minutes=="") { waitingtime_minutes = '0'; }
								
								maps_debug("Timing: "+waitingtime_hours+"h "+waitingtime_minutes+"m");
								
								// Validate inputs
								if(waitingtime_hours >= 0 && waitingtime_minutes >= 0 && is_numeric(waitingtime_hours)==true && is_numeric(waitingtime_minutes)==true) {
								
									var waitingtime = parseFloat(waitingtime_minutes) + (parseFloat(waitingtime_hours)*60);						

								}
								else {
									maps_debug("Free timing inputs didn't pass validation.");
									var waitingtime = "";
								}
								
							} else {
					    		var waitingtime = $("#waitingtime").val();
					    	}
				    		
				    		$(this).blur();
				    		$("#waitingtime").val("");
				    	
				    		if(waitingtime != "") {
				    			maps_debug("Adding a wating time for a place: "+waitingtime+" mins");
				    			
								show_loading_bar("<?php echo _("Adding..."); ?>");
				    	
				    			// Send an api call
								var apiCall = "api/?add_waitingtime="+waitingtime+"&place_id=<?php 
								
									echo $place["id"]; 
								
									if($user["logged_in"]===true) echo '&user_id='.$user["id"];
								
								?>";
								maps_debug("Calling API: "+apiCall);
								$.getJSON(apiCall, function(data) {
									
									hide_loading_bar();
									
									if(data.success == true) {
										maps_debug("Waiting time saved. Place "+data.point_id);
										showPlacePanel(<?php echo $place["id"]; ?>);
									}
									// Oops!
									else {
									    info_dialog("<?php echo _("Adding a waiting time failed.")."<br /><br />"._("Please try again!"); ?>", "<?php echo _("Error"); ?>", true);
									    maps_debug("Adding a waiting time failed. <br />- Error: "+data.error+"<br />- Data: "+data);
									}
									
								});
								
				    		} else {
								info_dialog("<?php echo _("Please add your waiting time first."); ?>", "<?php echo _("Error"); ?>", true);
				    		}
				    				    	
				    	});
				    	
				    	
						// Show a waiting time log
				    	$("a#show_waitingtime_log").click(function(e){ 
				    		e.preventDefault();
				    		$(this).blur();
				    		
				    		$("#waitingtime_log").html('<br /><img src="static/gfx/loading.gif" alt="<?php echo _("Loading"); ?>" />');
				    		
				    		// Get waitingtime log for this place
							$.ajax({ url: "ajax/waitingtimes.php?id=<?php echo $place["id"]; ?>", success: function(data){
								
								$("#waitingtime_log")
									.hide()
									.html(data)
									.slideDown("fast");
								
							}});
				    		
				    	});
				    	
				    		
				    });
				</script>
			</li>
		</ul>
	</li>
	
	
	<!-- Comments -->
	<li>
		<ul>
			<li>
				<div id="comments">
					<h3 style="margin: 0;" class="icon comments"><?php echo _("Comments"); ?> <small class="light">(<span id="comment_counter"><?php echo $place["comments_count"]; ?></span>)</small></h3>
					<ol id="comment_list">
				<?php if(!empty($place["comments"])): ?>
					<?php
					foreach($place["comments"] as $comment) {
						echo '<li class="comment';
						
						// If you're logged in, your own comments will get a special class
						if($user["logged_in"]===true && $user["id"]==$comment["user"]["id"]) { echo ' own_comment'; }
						
						echo '" id="comment-'.$comment["id"].'">';
						
						// Comment content
						echo Markdown($comment["comment"]);
						
						// Nick, date, remove etc.
						echo '<div class="meta"><strong>';
						
						if(isset($comment["user"]["nick"])) echo htmlspecialchars($comment["user"]["nick"]);
						elseif(isset($comment["user"]["name"])) echo htmlspecialchars($comment["user"]["name"]);
						else echo '<i>'._("Anonymous").'</i>';
						
						echo '</strong> &mdash; <span title="'.date(DATE_RFC822,strtotime($comment["datetime"])).'">'.date("j.n.Y",strtotime($comment["datetime"])).'</span>';
						
						// Show remove-link for logged in comments owner
						if($user["admin"]===true) {
							?>
							 <a href="#" onclick="removeComment('<?php echo $comment["id"]; ?>'); return false;" class="ui-icon ui-icon-trash align_right" title="<?php echo _("Remove comment permanently"); ?>"></a>
							 <a href="admin/?edit_comment=<?php echo $comment["id"]; ?>" class="ui-icon ui-icon-pencil align_right" title="<?php echo _("Edit comment"); ?>"></a>
							 <?php
						}
						elseif($user["logged_in"]===true && $user["id"]==$comment["user"]["id"]) {
							?>
							 <a href="#" onclick="removeComment('<?php echo $comment["id"]; ?>'); return false;" class="ui-icon ui-icon-trash align_right" title="<?php echo _("Remove comment permanently"); ?>"></a>
							<?php
						}
						
						echo '</div>';
						
						echo '</li>';
					}
					?>
				<?php endif; ?>
					</ol>
				
					<textarea id="write_comment" name="write_comment" rows="1" class="icon comment grey"><?php echo _("Leave a comment..."); ?></textarea>
					<div id="btn_comment_placeholder" style="display:block;padding-bottom:7px;clear: both;"></div>
				
				</div>
				<script type="text/javascript">
					// Write a comment
					$(function() {
				
						// When selecting the textarea for writing a comment
						$("#write_comment").focus(function(){
							
							// Add comment -button if it isn't there yet
							if($("#btn_comment_placeholder").text() == "") {
						
								maps_debug("Opening commenting.");
							
								$("#write_comment")
									.val("")
									.attr("rows","4")
									.removeClass("icon comment grey")
									.attr("style","width:100%;");
								
								$("#btn_comment_placeholder")
									.html('<?php 
										// Add a nick-field only for not-logged in users
										if($user===false): 
											?><input type="text" name="nick" id="nick" value="<?php echo _("Nickname"); ?>" class="align_left grey" size="14" maxlength="80" /><?php 
										else:
											?><strong title="<?php echo _("You are logged in. Your name will be visible for others."); ?>"><small class="align_left light"><?php echo $user["name"]; ?></small></strong><?php
										endif;
										
										?><button id="btn_comment" class="align_right smaller"><?php echo _("Comment"); ?></button><br />')
									.attr("style","clear: both; padding:5px 0;");
								
								<?php if($user===false): ?>
								$("#btn_comment_placeholder #nick").focus(function(){
									if($(this).val() == "<?php echo _("Nickname"); ?>") {
										$(this).val("").removeClass("grey");
									}
								});
								<?php endif; ?>
								
								
								$("#btn_comment").button({
				        		    icons: {
				        		        primary: 'ui-icon-comment'
				        		    }
								}).click(function(e) {
									e.preventDefault();
									maps_debug("Adding a comment...");
									
									if($("#write_comment").val() == "") {
										info_dialog("<?php echo _("Please write a comment first."); ?>", "<?php echo _("Comment missing"); ?>");
									} else {
									
										// Update comment to the DB
										//info_dialog("Adding comments isn't working yet, sorry.", "TODO");
										
										// Disable form during sending
										$("#btn_comment").button( "option", "disabled", true );
										$("#write_comment").attr("disabled","disabled");
										<?php if($user===false): ?>$("#btn_comment_placeholder #nick").attr("disabled","disabled");<?php endif; ?>
										show_loading_bar("<?php echo _("Sending..."); ?>");
												
										/*	API is listenin' for these:
										 * - place_id (required)
										 * - comment (required)
										 * - user_id (optional)
										 * - user_nick (optional)
										 */
										 
										// Get data from the form
										var post_comment = $("#write_comment").val();
										
										<?php if($user===false): ?>
										var post_nick = $("#btn_comment_placeholder #nick").val();
										
										// Don't send nickname if nick is default (we will use "anonymous" instead
										if(post_nick == "<?php echo _("Nickname"); ?>") { post_nick = ""; }
										<?php endif; ?>
										
										maps_debug("Comment place <?php echo $place["id"]; ?>");
										
										// Call API
										$.post('api/?add_comment', { place_id: "<?php echo $place["id"]; ?>", comment: post_comment, <?php if($user===false) { echo 'user_nick: post_nick'; } else { echo 'user_id: "'.$user["id"].'"'; } ?> }, 
											function(data) {

												hide_loading_bar();
												
												// Enable form again
												$("#write_comment").removeAttr("disabled");
												$("#btn_comment").button( "option", "disabled", false );
												<?php if($user===false): ?>$("#btn_comment_placeholder #nick").removeAttr("disabled");<?php endif; ?>
												
												// Comment added
												if(data.success == true) {
													maps_debug("Comment #"+data.id+" added to the place "+data.place_id+".");
													
													// Empty textarea
													$("#write_comment").val("");
													
													// Add newly added comment to the panel
													$("#comment_list").append('<li class="comment own_comment" id="comment-'+data.id+'">'+data.comment+'<div class="meta"><strong>'+data.user_nick+'</strong> &mdash; '+data.date+'<?php if($user["logged_in"]===true): ?><a href="#" onclick="removeComment('+data.id+'); return false;" class="ui-icon ui-icon-trash align_right" title="<?php echo _("Remove comment permanently"); ?>"></a><?php endif; ?></div></li>');
												
													var current_comment_count = $("#comments #comment_counter").text();
													$("#comments #comment_counter").text(parseInt(current_comment_count)+1);
												}
												// Oops!
												else {
													info_dialog("<?php echo _("Adding a comment failed.")."<br /><br />"._("Please try again!"); ?>", "<?php echo _("Error"); ?>", true);
													maps_debug("Adding comment failed. <br />- Error: "+data.error+"<br />- Data: "+data);
												}

											}, "json"
										); // post end
										 
									} // else if comment was empty * end
									
								}); // button click end
								
							} // add comment-button on focus 
							
						}); // focus listener

					});
				</script>
			</li>
		</ul>
	</li>


	<!-- infolinks -->
	<li>
		<ul>
			<li class="cursor_hand">
				<h4 class="icon magnifier" style="display:inline;" id="more_about_title"><?php echo _("More about this place"); ?></h4>
				<a href="#" id="toggle_extralinks" class="ui-icon ui-icon-triangle-1-e align_right" title="<?php echo _("Toggle"); ?>"></a>
				
				<script type="text/javascript">
					// Toggle search place
					$(function() {
					
						var place_weather_info = $("#extralinks #place_weather #place_weather_info");
						
						$("#more_about_title, #toggle_extralinks").click(function(e){
							e.preventDefault();
						
							if($("#extralinks").is(":hidden")) {
								
								maps_debug("Open place's extra info.");
											
								$("#toggle_extralinks").removeClass("ui-icon-triangle-1-e").addClass("ui-icon-triangle-1-s"); 
								$(this).blur();
								$("#extralinks").slideDown();
								
								
								// If no weather info yet, get data from wunderground.com
								if(place_weather_info.hasClass("no_weather")) {
								
									maps_debug("Loading the weather info for the place from wunderground...");
									
									var weather_error_html = '<?php error_sign(_("No weather info..."), false); ?>'; // TODO: something nicer to here, since might be a bit common error to show
									 
									//$.getJSON('ajax/wefather.php?lat=<?php echo $place["lat"]; ?>&lon=<?php echo $place["lon"]; ?>', function(data) {	
									$.ajax({
										// Define AJAX properties.
										method: "get",
										url: 'ajax/weather.php?lat=<?php echo $place["lat"]; ?>&lon=<?php echo $place["lon"]; ?>',
										dataType: "json",
										timeout: 7000, // timeout in milliseconds; 1s = 1000ms
									 
										// Got a place
										success: function(data){		
									
									    	if(data.error==true) {
									    	    maps_debug("PHP Error when loading weather information.");
									    	    place_weather_info.html(weather_error_html).delay(5000).slideUp('slow');
									    	}
									    	else {
											    maps_debug("Got the weather!");
											    place_weather_info.html('<img src="'+data.weather.icon+'" alt="" class="align_right" />'+
											    		data.weather.status+'<br />'+
											    		'<b><?php echo _("Temperature"); ?>:</b> '+data.weather.temperature_c+'&deg;C / '+data.weather.temperature_f+'&deg;F<br />'+
											    		'<b><?php echo _("Humidity"); ?>:</b> '+data.weather.relative_humidity+'<br />'+
											    		'<b><?php echo _("Wind"); ?>:</b> <span title="<?php echo _("Direction"); ?>">'+data.weather.wind_degrees+'&deg;</span>, <span title="<?php echo _("Intensity"); ?>">'+data.weather.wind_mph+'<?php echo _("m/s"); ?></span><br />'+
											    		'<b><?php echo _("Air pressure"); ?>:</b> '+data.weather.pressure_in+' in ('+data.weather.pressure_mb+' mb)');
									    	}
									    
										},
										// Didn't find anything...
										error: function( objAJAXRequest, strError ){
											maps_debug("JSON weather query didn't find anything. Error type: "+strError);
									        place_weather_info.html(weather_error_html).delay(5000).slideUp('slow');
										}
									});
									
								}
								
								
							} else {
							
								maps_debug("Close place's extra info.");
								
								$("#toggle_extralinks").removeClass("ui-icon-triangle-1-s").addClass("ui-icon-triangle-1-e"); 
								$(this).blur();
								$("#extralinks").slideUp();
							}
						
						});
					
					});
				</script>
			</li>
	    	
	    	<div class="hidden" id="extralinks">
	    	
	    	<!-- meta info -->
			<li>
	    		<small class="inset">
				<?php
					// When marker was added and who added it					
					// Name
					if(isset($place["user"]["name"])) {
						echo _("Added by").' <strong>'.htmlspecialchars($place["user"]["name"]).'</strong>';
					
						if(!empty($place["datetime"])) ' &mdash; ';
					}
					elseif(!empty($place["datetime"])) echo _("Added at")." ";
					
					// Date
					if(!empty($place["datetime"])) {
						echo '<span title="'.date(DATE_RFC822,strtotime($place["datetime"])).'">'.date("j.n.Y",strtotime($place["datetime"])).'</span>';
					}
					
					if(isset($place["user"]["name"]) OR !empty($place["datetime"])) echo '<br />';
					
					// Elevation
					if($place["elevation"]=="0" OR !empty($place["elevation"])) echo _("Elevation").': '.$place["elevation"].' '._("meters").'<br />';
					
				?>
	    		</small>
			</li>
	    	
	    	<!-- Weather info will be loaded on fly when opening #extralinks -->
	    	<li id="place_weather">
	    		<small>
	    			<b class="icon weather" style="padding-top: 5px;display:block;"><?php printf(_("Weather near %s"), $place["location"]["locality"]); ?></b>
					<div class="inset">
	    				<span id="place_weather_info" class="no_weather"><img src="static/gfx/loading.gif" alt="<?php echo _("Loading"); ?>" /><br /></span>
	    				<br /><a href="http://www.wunderground.com/cgi-bin/findweather/getForecast?query=<?php echo $place["lat"]; ?>,<?php echo $place["lon"]; ?>" target="_blank"><?php echo _("Weather from Wunderground.com"); ?></a>
	    			</div>
	    		</small>
	    	</li>
	    	
	    	<!-- place link -->
			<li>
				<div class="icon link"><label for="link_place"><small><?php echo _("Link to this place:"); ?></small></label></div>
				<input type="text" id="link_place" value="<?php echo htmlspecialchars($place["link"]); ?>" class="copypaste" />
				<script type="text/javascript">
					$(function() {
						// Select all from textarea on focus
						$(".copypaste").focus(function(){
						    this.select();
						});
					});
				</script>
				
			</li>
			
	    	
	    	<!-- city info -->
	    	<?php if(!empty($place["location"]["locality"])): ?>
			<li>
	    		<small>
	    			<b class="icon building" style="padding-top: 5px;display:block;"><?php echo $place["location"]["locality"]; ?></b>
	    			<div class="inset">
	    			<a target="_blank" href="http://hitchwiki.org/en/index.php?title=Special%3ASearch&search=<?php echo urlencode($place["location"]["locality"]); ?>&go=Go">Hitchwiki</a>, 
	    			<a target="_blank" href="http://en.wikipedia.org/wiki/Special:Search?search=<?php echo urlencode($place["location"]["locality"]); ?>">Wikipedia</a>, 
	    			<a target="_blank" href="http://wikitravel.org/en/Special:Search?search=<?php echo urlencode($place["location"]["locality"]); ?>&go=Go">Wikitravel</a>
	    			</div>
	    		</small>
	    	</li>
	    	<?php endif; ?>

			<!-- country info -->
	    	<?php if(!empty($place["location"]["country"]["name"])): ?>
	    	<li>
	    		<small>
	    			<b class="icon world" style="padding-top: 5px;display:block;"><?php echo $place["location"]["country"]["name"]; ?></b>
	    			<div class="inset">
	    			<a target="_blank" href="http://hitchwiki.org/en/index.php?title=Special%3ASearch&search=<?php echo urlencode($place["location"]["country"]["name"]); ?>&go=Go">Hitchwiki</a>, 
	    			<a target="_blank" href="http://en.wikipedia.org/wiki/Special:Search?search=<?php echo urlencode($place["location"]["country"]["name"]); ?>">Wikipedia</a>, 
	    			<a target="_blank" href="http://wikitravel.org/en/Special:Search?search=<?php echo urlencode($place["location"]["country"]["name"]); ?>&go=Go">Wikitravel</a>, 
	    			<a target="_blank" href="http://www.couchsurfing.org/statistics.html?country_name=<?php echo urlencode($place["location"]["country"]["name"]); ?>">CouchSurfing</a>
	    			</div>
	    		</small>
			</li>
	    	<?php endif; ?>
	    	
	    	<!-- coordinate related info -->
	    	<li>
				<small id="coordinates">
				    <b class="icon map" style="padding-top: 3px;display:block;">
				    	<span class="lat" title="<?php echo _("Latitude"); ?>"><?php echo $place["lat"]; ?></span>, 
				    	<span class="lon" title="<?php echo _("Longitude"); ?>"><?php echo $place["lon"]; ?></span>
				    </b>
				    <div class="inset">
	    			<a href="http://maps.google.com/?q=<?php echo $place["lat"].",".$place["lon"]; ?>" target="_blank">Google</a>, 
				    <a href="http://www.bing.com/maps/default.aspx?v=2&amp;cp=<?php echo $place["lat"]."~".$place["lon"]; ?>&amp;style=r&amp;lvl=12&amp;sp=Point.<?php echo $place["lat"]."_".$place["lon"]."_".urlencode($place["location"]["locality"]); ?>___" target="_blank">Bing</a>, 
					<a href="http://www.openstreetmap.org/index.html?mlat=<?php echo $place["lat"]; ?>&amp;mlon=<?php echo $place["lon"]; ?>&amp;zoom=12&amp;layers=B000FTF" target="_blank">OpenStreetMap</a>, 
					<a href="http://www.wikimapia.org/#lat=<?php echo $place["lat"]; ?>&amp;lon=<?php echo $place["lon"]; ?>&amp;z=12&amp;l=24&amp;m=w" target="_blank">Wikimapia</a>, 
					<a href="http://www.panoramio.com/map/#lt=<?php echo $place["lat"]; ?>&amp;ln=<?php echo $place["lon"]; ?>&amp;z=0&amp;k=0&amp;a=1&amp;tab=2" target="_blank">Panoramio</a>,
					<a href="http://www.flickr.com/nearby/<?php echo $place["lat"].",".$place["lon"]; ?>" target="_blank">Flickr</a>, 
					<a href="http://maps.google.com/maps?&amp;q=<?php echo $place["lat"].",".$place["lon"]; ?>&amp;spn=0.1,0.1&amp;output=kml" target="_blank">Google Earth</a>
					</div>
				</small>
			</li>
			
	    	<!-- download -->
	    	<li>
				<small>
				<b class="icon page_white_put" style="padding-top: 3px;display:block;"><?php echo _("Download marker as a file"); ?></b>
					<div class="inset">
	    			<a href="./api/?format=gpx&amp;download=hitchhiking_place_<?php echo $place["id"]; ?>&amp;place=<?php echo $place["id"]; ?>" type="application/gpx+xml" class="icon gpx">GPX</a> &nbsp; 
					<a href="./api/?format=kml&amp;download=hitchhiking_place_<?php echo $place["id"]; ?>&amp;place=<?php echo $place["id"]; ?>" type="application/vnd.google-earth.kml+xml" class="icon kml">KML</a> &nbsp;
					<!--
					<a href="./api/?format=kmz&amp;download=hitchhiking_place_<?php echo $place["id"]; ?>&amp;place=<?php echo $place["id"]; ?>" type="application/vnd.google-earth.kmz" class="icon gmz">KMZ (<?php echo _("Zipped"); ?> KML)</a> 
					-->
					</div>
				</small>
			</li>
			

		</div>
		
		</ul>
	</li>
	<?php 
	/*
	 * Facebook btn will be published only when webpage is at it's final destination, so we won't get wrong URL history to anywhere.
	 *
	 * Tried to publish it, but it just gives me "recommends Hitchwiki Maps" and link to /maps/ - not to the place. Trying again later. - 16.12.2010 Mikael
	<li>
		<ul>
			<li title="<?php echo _("Recommend this place for your Facebook contacts"); ?>" id="share_place">
				<!-- Facebook BTN -->
					<iframe src="http://www.facebook.com/plugins/like.php?locale=<?php echo $settings["language"]; ?>&amp;href=<?php echo urlencode($place["link"]); ?>&amp;layout=button_count&amp;show_faces=true&amp;width=200&amp;action=recommend&amp;colorscheme=light&amp;height=21" scrolling="no" frameborder="0" style="border:none; overflow:hidden; width:200px; height:21px; margin: 7px 0;" allowTransparency="true"></iframe>
			</li>
			
		</ul>
	</li>
	*/ ?>


	<?php 
	// Show admin menu
	if($user["admin"]===true): ?>
	<li>
		<ul>
			<li class="cursor_hand">
				<h4 class="icon wrench" style="display:inline;" id="for_admins_title"><?php echo _("Administration"); ?></h4>
				<a href="#" id="toggle_for_admins" class="ui-icon ui-icon-triangle-1-e align_right" title="<?php echo _("Toggle"); ?>"></a>
				
				<script type="text/javascript">
					// Toggle search place
					$(function() {
					
						$("#for_admins_title, #toggle_for_admins").click(function(e){
							e.preventDefault();
						
							if($("#for_admins").is(":hidden")) {
								
								$("#toggle_for_admins").removeClass("ui-icon-triangle-1-e").addClass("ui-icon-triangle-1-s"); 
								$(this).blur();
								$("#for_admins").slideDown();
								
							} else {
							
								$("#toggle_for_admins").removeClass("ui-icon-triangle-1-s").addClass("ui-icon-triangle-1-e"); 
								$(this).blur();
								$("#for_admins").slideUp();
							}
						
						});
					
					});
				</script>
			</li>
	    	
	    	<div class="hidden" id="for_admins">
	    	
			<li>
					<ul>
						<li>
							<label for="place_id">Place ID:</label> <input type="text" size="6" style="width: 50px;" value="<?php echo $place["id"]; ?>" id="place_id" class="copypaste" />
							<script type="text/javascript">
								$(function() {
									// Select all from input on focus
									$("#place_id").focus(function(){
									    this.select();
									});
								});
							</script>
						</li>
						<li><a href="admin/?page=places&amp;remove=<?php echo $place["id"]; ?>" onclick="confirm('Are you sure?');"><?php echo _("Remove place"); ?></a></li>
						<li><a href="admin/?page=places&amp;edit=<?php echo $place["id"]; ?>"><?php echo _("Edit place"); ?></a></li>
						<?php if(!empty($place["user"]["id"])): ?><li><a href="admin/?users&amp;user=<?php echo $place["user"]["id"]; ?>"><?php echo _("See user"); ?></a></li><?php endif; ?>
					</ul>
			</li>
		</ul>
	</li>
	<?php endif; ?>
</ul>


<?php 
// Error when getting place info, show error popup
else: ?>

<script type="text/javascript">
    $(function() {
		maps_debug("Error loading marker data from the PHP-side.");
		info_dialog("<?php echo _("Sorry, but the place cannot be found.<br /><br />The place you are looking for might have been removed or is temporarily unavailable."); ?>", "<?php echo _("The place cannot be found"); ?>", true);
    	hidePlacePanel();
	});
</script>

<?php endif; ?>

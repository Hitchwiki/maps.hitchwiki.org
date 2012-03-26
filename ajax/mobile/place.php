<?php
/*
 * Hitchwiki Mobile Maps: place.php
 * Show a place panel
 */

/*
 * Load config to set language and stuff
 */
require_once "../../config.php";

/* 
 * Gather data
 */
$place = (isset($_GET["id"]) && is_id($_GET["id"])) ? get_place($_GET["id"],true,true) : false;

?>
<!-- Place info: -->
<div data-role="dialog" id="place_info" data-transition="pop">
    <div data-role="header" data-theme="e">
	    <h1><?php
	    
	    	if($place["error"] == true OR $place == false) echo _("Hitchhiking spot");
	    	else {
	    
	    		// Flag
	    		if(!empty($place["location"]["country"]["iso"])) echo '<img src="../static/gfx/flags/'.strtolower($place["location"]["country"]["iso"]).'.png" /> ';
	    		
	    		// Town/City
	    		if(!empty($place["location"]["locality"])) echo $place["location"]["locality"].", ";
	    		
	    		// Country
	    		if(!empty($place["location"]["country"]["name"])) echo $place["location"]["country"]["name"];

			}
			
	    ?></h1>
    </div>
    <div data-theme="c" data-role="content">
    
	<?php

/* 
 * Error when getting place info
 */
if($place["error"] == true OR $place == false) { ?>

	<div data-theme="e"><?php echo _("Sorry, but the place cannot be found.<br /><br />The place you are looking for might have been removed or is temporarily unavailable."); ?></div>
	<script type="text/javascript">
			maps_debug("Error loading marker data from the PHP-side.");
			//$.mobile.changePage("#mappage");
	</script>
	<?php 
} else {


/*
 * Returns an info-array about logged in user (or false if not logged in) 
 */
$user = current_user();

/* 
 * Print stuff out in HTML:
 */
?>

<ul data-role="listview" id="place_info_list" data-divider-theme="e">

<?php /*
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
					    		//zoomMapIn(<?php echo $place["lat"]; ?>, <?php echo $place["lon"]; ?>, 16);
					    	});
					    
					    });
					</script>
				</div>
			</li>
		</ul>
	</li>
*/ ?>

	<!-- description in different languages -->
	<li data-role="list-divider"><?php echo _("Description"); ?></li>
	<li>

	    <?php if(count($place["description"]) > 1): ?>
	    <select name="select_description" id="select_description">
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
	    <?php endif; ?>
	    
	    <div id="place_descriptions">
	        <?php
	        // Print out lang textareas
	        foreach($place["description"] as $code => $description) {
	            echo '<div id="tab-'.$code.'" class="place_description">';
	        	
	        	//if(!empty($place["description"][$code])) {
	        		
	        		// Date 
	    			if(!empty($description["datetime"])) {
	    			    echo '<p class="ui-li-aside">';
	    				$description_date = date("j.n.Y",strtotime($description["datetime"]));
	    			    
	    			    if($place["description"][$code]["versions"] > 1) {
	    			    	printf(_('Description edited %s'), $description_date);
	    			    }
	    			    else {
	    			    	printf(_('Description written %s'), $description_date);
	    			    }
	    			    echo '</p>';
	    			}
	    			
	        		echo Markdown($description["description"]);
	        		
	    			
	        	//}
	        	echo '</div>';
	        	
	        } //foreach 
	        ?>
	    </div>
	     <?php if(count($place["description"]) > 1): ?>
	    <script type="text/javascript">
	    $(function() {
	    
	    	// Descreption language selection
	        $("#descriptions .place_description").hide();
	        $("#descriptions #tab-<?php echo $selected_tab; ?>").show();
	        
	        $("#select_description").change( function () { 
	        	var selected_language = $(this).val();
	        	$(this).blur();
	        	$("#descriptions .place_description").hide();
	        	$("#descriptions #tab-"+selected_language).show();
	    		stats("read_description/"+selected_language);
	        });
	        
	    	
	    });
	    </script>
	    <?php endif; ?>
	</li>

	<!-- Hitchability -->
	<li data-role="list-divider">
		<?php echo _("Hitchability"); ?><span class="ui-li-count"><?php 
		echo hitchability2textual($place["rating"]);
		//echo hitchability2numeric($place["rating_stats"]["exact_rating"]); 
	?> <b style="font-size:2em; line-height:13px;" class="hitchability_color_<?php echo $place["rating"]; ?>">&bull;</b></span></li>
	<li data-role="fieldcontain">
	    
	    <?php 

	    // Check if user has already rated this point, and if, what did one rate?
	    $users_rating = false;
	    if($user["logged_in"]===true) {
	    
	        start_sql();
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
	    } //logged_in?
	
		?>

		<div class="ui-grid-a">
			<div class="ui-block-a">
	    		 <fieldset data-role="controlgroup" id="rate">
	    			<legend><?php echo _("Your opinion..."); ?></legend>
	    			<?php
	    				// Rating list
	    				for($i=1; $i <= 5; $i++) {
				
	    		         	echo '<input type="radio" name="rate" id="rate_'.$i.'" value="'.$i.'"';
	    		         	if($users_rating==$i) echo ' checked="checked"';
	    		         	echo ' />';
	    		     		
	    		     		echo '<label for="rate_'.$i.'">'.hitchability2textual($i).'</label>';
	    		     	}//for
	    			?>
	    		</fieldset>
	    	</div>
			<div class="ui-block-b">
	    	<?php 
	    	
	    	// User has rated for the place
	    	if(!empty($users_rating_date)) {
	    		echo '<p>'._("You rated for this place").' <time title="'.date(DATE_RFC822, strtotime($users_rating_date)).'">'.date("j.n.Y", strtotime($users_rating_date)).'</time></p>';
	    	}
	    	
	    	// Remove my rating btn
	    	if($users_rating==true) {
	    	    echo '<button data-mini="true" id="remove_my_rating" data-icon="delete">'._("Remove my rating").'</button>';
	    	}
	    	
	    	// Link to show ratings -log
	    	if(!empty($place["rating_stats"]["rating_count"])) {
	    		echo '<button data-mini="true" id="show_rating_log" data-icon="arrow-d">'.sprintf(ngettext("See %d vote", "See %d votes", $place["rating_stats"]["rating_count"]), $place["rating_stats"]["rating_count"]).'</button>';
	    	}
	    	
	    	?>
	    	</div>
	    </div>
	    
	    <div id="rating_log" class="ui-body ui-body-d" style="display:none;"></div>

		<script type="text/javascript">
		    	// Rate a place
		    	$("#rate input").click( function () { 
		    	
		    		var rate = $(this).val();
		    		//$(this).blur();
		    	
		    		maps_debug("Rating a place with "+rate);
		    		
		    		// Send an api call
		    		var apiCall = basehref+"api/?rate="+rate+"&place_id=<?php 
		    		
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
		    		        	
		    	});
		    	
		    	// Remove rating
		    	$("#remove_my_rating").click( function () { 
		    	    var confirm_remove = confirm("<?php echo _("Are you sure you want to remove this record?"); ?>")
		    	    
		    	    var remove_id = "<?php echo $place["id"]; ?>";
		    	    
	        	    maps_debug("Asked to remove rating for the place "+remove_id);
		    	    stats("rating/remove/");
		    	
		    	    if(confirm_remove) {
		    	
		    	    	// Call API
		    	    	$.getJSON(basehref+'api/?remove_rating&place_id='+remove_id, function(data) {
		    	    	
		    	    		if(data.success == true) {
		    	    	
	        	    			maps_debug("Rating for the place "+remove_id+" removed.");
		    	    		
		    	    			// Fade rating away
	        	    			//$("#timing_list #timing-"+remove_id).fadeOut("slow");
	        	    			showPlacePanel(<?php echo $place["id"]; ?>);
	        	    	
	        	    			
	        	    		// Produces an error popup if current logged in user doesn't have permissions or some other error happened
		    	    		} else {
		    	    			info_dialog("<?php echo _("Could not remove a record due to an error. Please try again!"); ?>", "<?php echo _("Error"); ?>", true);
	        	    			maps_debug("Could not remove rating for the place "+remove_id+". Error: "+data.error_description);
		    	    		}
		    	    	
		    	    	});
		    	    
		    	    }
		    	});
		    	
		    	
		    	// Show a rating log
		    	$("#show_rating_log").click(function(e){ 
		    		//e.preventDefault();
		    		//$(this).blur();
		    		$(this).hide();
		    		
		    		$.mobile.showPageLoadingMsg();
		    		
		    		// Get waitingtime log for this place
		    		$.ajax({ url: basehref+"ajax/mobile/hitchability_log.php?id=<?php 
		    			echo $place["id"]; 
		    			
		    			// If more than 1 rating, show more complicated statistics
		    			if($place["rating_stats"]["rating_count"] > 1) echo '&stats';
		    			
		    		?>", success: function(data){
		    			
		    			$("#rating_log")
		    				.hide()
		    				.html(data)
		    				.slideDown("fast")
		    				.trigger( 'updatelayout' );
		    			
		    			$.mobile.hidePageLoadingMsg();
		    			
		    		}});
		    		
		    	});

		</script>
				
	</li>


	<!-- Waiting time -->
	<li data-role="list-divider"><?php echo _("Waiting time"); ?><span class="ui-li-count"><?php 
			//'._("Average").'

			if($place["waiting_stats"]["count"] > 0) echo $place["waiting_stats"]["avg_textual"];
			else echo _("Unknown");
			
	?></span></li>
	<li data-role="fieldcontain">
	
		<input type="range" value="0" min="0" max="100" name="waitingtime_hours" id="waitingtime_hours" />
		<label for="waitingtime_hours"><?php echo _("hours"); ?></label>
		
		<br />
		
		<input type="range" value="0" min="0" max="100" name="waitingtime_minutes" id="waitingtime_minutes" />
		<label for="waitingtime_minutes"><?php echo _("minutes"); ?></label>

		<br />

		<button id="waitingtime_add" data-role="button" data-inline="true" data-mini="true"><?php echo _("Add"); ?></button>
			
		<?php
		    if($place["waiting_stats"]["count"] > 0) {
		    	echo '<button id="show_waitingtime_log" data-mini="true" data-button="true" data-inline="true">'; 
		    	printf(ngettext("See %d experience", "See %d experiences", $place["waiting_stats"]["count"]), $place["waiting_stats"]["count"]);
		    	echo '</button>';
		    }
		?>
		<div id="waitingtime_log"></div>
			
			<script type="text/javascript">
			    $(function() {
			    
			    	/* 
			    	 * Save timing
			    	 */
			    	 /*
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
			    			var apiCall = basehref+"api/?add_waitingtime="+waitingtime+"&place_id=<?php 
			    			
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
			    				    maps_debug("Adding a waiting time for the place <?php echo $place["id"]; ?> failed. <br />- Error: "+data.error_description);
			    				}
			    				
			    			});
			    			
			    		} else {
			    			info_dialog("<?php echo _("Please add your waiting time first."); ?>", "<?php echo _("Error"); ?>", true);
			    		}
			    				    	
			    	});
			    	*/
			    	
			    	
			    	// Show a waiting time log
			    	
			    	$("#show_waitingtime_log").click(function(e){ 
			    		e.preventDefault();
			    		//$(this).blur();
			    		$(this).hide();
			    		
			    		
				    	$.mobile.showPageLoadingMsg();
				    		
			    		// Get waitingtime log for this place
			    		$.ajax({ url: basehref+"ajax/mobile/waitingtimes_log.php?id=<?php echo $place["id"]; ?>", success: function(data){
			    			
			    			$("#waitingtime_log")
			    				.hide()
			    				.html(data)
			    				.slideDown("fast")
								.trigger( 'updatelayout' );
			    			
			    			$.mobile.hidePageLoadingMsg();
			    			
			    		}});
			    		
			    	});
			    	
			    	
			    		
			    });
			</script>
	
	</li>
	
	<?php /*
	<li>
	
		<!-- Comments -->
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
						elseif(isset($comment["user"]["name"])) echo '<a href="./?page=profile&amp;user_id='.$comment["user"]["id"].'" onclick="open_page(\'profile\', \'user_id='.$comment["user"]["id"].'\'); return false;" title="'._("Profile").'">'.htmlspecialchars($comment["user"]["name"]).'</a>';
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
												
										// * API is listenin' for these:
										// * - place_id (required)
										// * - comment (required)
										// * - user_id (optional)
										// * - user_nick (optional)
										// *
										 
										// Get data from the form
										var post_comment = $("#write_comment").val();
										
										<?php if($user===false): ?>
										var post_nick = $("#btn_comment_placeholder #nick").val();
										
										// Don't send nickname if nick is default (we will use "anonymous" instead
										if(post_nick == "<?php echo _("Nickname"); ?>") { post_nick = ""; }
										<?php endif; ?>
										
										maps_debug("Comment place <?php echo $place["id"]; ?>");
										
										// Call API
										$.post(basehref+'api/?add_comment', { place_id: "<?php echo $place["id"]; ?>", comment: post_comment, <?php if($user===false) { echo 'user_nick: post_nick'; } else { echo 'user_id: "'.$user["id"].'"'; } ?> }, 
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
													maps_debug("Adding comment failed. <br />- Error: "+data.error_description+"<br />- Data: "+data);
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
		<!-- /comments -->
		
	</li>
	*/ ?>
	

	<!-- Info and download -->
	<li data-role="list-divider"><?php echo _("Download marker as a file"); ?></li>
	<li>
		<div class="ui-grid-a">
			<div class="ui-block-a">
				<div data-role="controlgroup" data-type="horizontal">
					<a data-role="button" data-mini="true" href="./api/?format=gpx&amp;download=hitchhiking_place_<?php echo $place["id"]; ?>&amp;place=<?php echo $place["id"]; ?>" rel="external" type="application/gpx+xml">GPX</a>
					<a data-role="button" data-mini="true" href="./api/?format=kml&amp;download=hitchhiking_place_<?php echo $place["id"]; ?>&amp;place=<?php echo $place["id"]; ?>" rel="external" type="application/vnd.google-earth.kml+xml">KML</a>
					<!--
					<a href="./api/?format=kmz&amp;download=hitchhiking_place_<?php echo $place["id"]; ?>&amp;place=<?php echo $place["id"]; ?>" type="application/vnd.google-earth.kmz">KMZ (<?php echo _("Zipped"); ?> KML)</a>
					-->
				</div>
			</div>
			<div class="ui-block-b">
			
	    	<?php
	    	// When marker was added and who added it					
	    	// Name
	    	if(isset($place["user"]["name"])) {
	    		echo "&bull; "._("Added by").'<a href="./?page=profile&amp;user_id='.$place["user"]["id"].'" onclick="open_page(\'profile\', \'user_id='.$place["user"]["id"].'\'); return false;" title="'._("Profile").'">'.htmlspecialchars($place["user"]["name"]).'</a>';
	    	
	    		if(!empty($place["datetime"])) echo ' &mdash;';
	    	}
	    	elseif(!empty($place["datetime"])) echo "&bull; "._("Added at");
	    	
	    	// Date
	    	if(!empty($place["datetime"])) {
	    		echo ' <span title="'.date(DATE_RFC822,strtotime($place["datetime"])).'">'.date("j.n.Y",strtotime($place["datetime"])).'</span>';
	    	}
	    	
	    	if(isset($place["user"]["name"]) OR !empty($place["datetime"])) echo '<br />';
	    	
	    	// Elevation
	    	if($place["elevation"]=="0" OR !empty($place["elevation"])) echo "&bull; "._("Elevation").': '.$place["elevation"].' '._("meters").'<br />';
	    	
	    	?>
			</div>
		</div>
	</li>

</ul>


<?php } /* No error? */ ?>

		<div style="text-align:center;">
		    <p><br/><br/><a href="./#mappage" data-icon="arrow-l" data-direction="reverse" data-role="button" data-inline="true" data-theme="e"><?php echo _("Map"); ?></a></p>
		</div>
        
    </div>
    		
</div><!-- /dialog -->
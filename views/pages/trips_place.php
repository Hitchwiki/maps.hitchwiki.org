<?php

echo info_sign("This feature is under development and visible only for admins.",false);

#$lines = gather_log();

?>

<h2>Place, city, Country</h2>
					
← <a href="#" onclick="open_page('trips'); return false;"><?php echo _("Back to listing"); ?></a>

<ol class="trips">

    <li id="marker_id">
    
    	<div class="datetime">
    		<span class="day">4th</span> 
    		<span class="month">Mar</span> 
    		<span class="year">2011</span>
    	</div>
    	
    	<div class="trip_map"><br /><br /><?php echo _("Loading..."); ?></div>
    	
    	<div class="place_info">
    	
    		<ul class="meta">
    			<li class="icon hitchability_3"><?php echo _("Hitchability"); ?>: Good</li>
    			<li class="icon time"><?php echo _("Waiting time"); ?>: 1h 4m</li>
    		</ul>
    		
    		<div class="trip_comments">
    		
    			<h3 style="margin: 0;" class="icon comments"><?php echo _("Comments"); ?> <small class="light">(<span id="comment_counter">0</span>)</small></h3>
    		
    			...
    		
    		</div><!-- /trip_comments -->

    	</div><!-- /meta_and_comments-->
    	
    	<div class="make_hitchplace">
    		<a href="#" class="yes_please png">Make place a hitchhiking spot</a>
    		<a href="#" class="no_thanks meta light"><i>No thanks</i></a>
    	</div>
    	
    </li>

</ol>
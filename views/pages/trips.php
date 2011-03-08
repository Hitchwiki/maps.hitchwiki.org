
<?= info_sign("This feature is under development and visible only for admins.",false); ?>


<h2><?php echo _("My trips	"); ?></h2>

<a href="#"><b><?php echo _("My trips"); ?></b></a> &bull; 
<a href="#"><?php echo _("Countries visited"); ?></a> &bull; 
<a href="#">Mountains</a> &bull; 
<a href="#"><?php echo _("Import"); ?></a> &bull; 


<!-- pagination --> 
<ul class="pagination">
    <li class="backwards"><span>&lsaquo;</span></li>
    <li class="num selected"><a href="#">1</a></li>
    <li class="num"><a href="#">2</a></li>
    <li class="num"><a href="#">3</a></li>
    <li class="num"><a href="#">4</a></li>
    <li class="num"><a href="#">5</a></li>
    <li>&bull;&bull;&bull;</li>
    <li class="num"><a href="#">20</a></li>

    <li class="forwards"><a href="#">&rsaquo;</a></li>

    <!-- timescale selector -->
    <li class="special timescale">
    	<label for="date_from" class="meta"><?php echo _("From"); ?></label> <input type="text" class="meta" value="2.1.2010" size="10" name="date_from" id="date_from" style="text-align: center;" />
    	&nbsp;
    	<label for="date_to" class="meta"><?php echo _("To"); ?></label> <input type="text" class="meta" value="2.1.2011" size="10" name="date_to" id="date_to" style="text-align: center;" />
    </li>	
    
    <!-- per page selector -->
    <li class="special perpage">
    	<select name="trips" id="trips_2" class="meta small">
    		<option value="10"><?php echo sprintf(_("%d per page"), 10); ?></option>
    		<option value="20"><?php echo sprintf(_("%d per page"), 20); ?></option>
    		<option value="50"><?php echo sprintf(_("%d per page"), 50); ?></option>
    		<option value="100"><?php echo sprintf(_("%d per page"), 100); ?></option>
    	</select>
    </li>
</ul>
<!-- /pagination -->




<ol class="trips">

    <li id="marker_id">
    
    	<div class="datetime">
    		<span class="day">4th</span> 
    		<span class="month">Mar</span> 
    		<span class="year">2011</span>
    	</div>
    	
    	<div class="place">
    		<h4><a href="#" onclick="open_page('trips_place'); return false;">Place, city, Country</a></h4>
			
    		<ul class="meta">
    			<li class="icon thumb_up"><?php echo _("Hitchability"); ?>: Good</li>
    			<li class="icon time">Waiting time: 1h 4m</li>
    		</ul>
    	</div>

    	<div class="make_hitchplace">
    		<a href="#" class="yes_please png">Make place a hitchhiking spot</a>
    		<a href="#" class="no_thanks meta light"><i><?php echo _("No thanks"); ?></i></a>
    	</div>
    	
    </li>
    <li id="marker_id">
    
    	<div class="datetime">
    		<span class="day">4th</span> 
    		<span class="month">Mar</span> 
    		<span class="year">2011</span>
    	</div>
    	
    	
    	<div class="place">
    		<h4><a href="#" onclick="open_page('trips_place'); return false;">Place, city, Country</a></h4>
    		<ul class="meta">
    			<li class="icon thumb_up">Hitchability: Good</li>
    		</ul>
    	</div>
    	

    	<div class="make_hitchplace">
    		<a href="#" class="yes_please png">Make place a hitchhiking spot</a>
    		<a href="#" class="no_thanks meta light"><i>No thanks</i></a>
    	</div>
    
    </li>
    <li id="marker_id">
    
    	<div class="datetime">
    		<span class="day">4th</span> 
    		<span class="month">Mar</span> 
    		<span class="year">2011</span>
    	</div>

    	<div class="place">
    		<h4><a href="#" onclick="open_page('trips_place'); return false;">Place, city, Country</a></h4>
    		<ul class="meta">
    			<li class="icon thumb_up">Hitchability: Good</li>
    			<li class="icon time">Waiting time: 1h 4m</li>
    			<li class="icon comment">1 comment</li>
    		</ul>
		</div>
    
    </li>

    <li id="marker_id">
    
    	
    	<div class="datetime">
    		<span class="day">4th</span> 
    		<span class="month">Mar</span> 
    		<span class="year">2011</span>
    	</div>
    	<div class="datetime_mdash">-</div>
    	<div class="datetime">
    		<span class="day">7th</span> 
    		<span class="month">Feb</span> 
    		<span class="year">2011</span>
    	</div>
    	
    	<div class="place title">
    		<h4><a href="#" onclick="open_page('trips_place'); return false;">Trip title lorem ipsum</a></h4>
    		<a href="#" class="toggle_places closed light">See 3 places in Poland, Germany and Lithuania</a>
    	</div>
    	
    </li>


    <li id="marker_id" class="open">
    
    	
    	<div class="datetime">
    		<span class="day">4th</span> 
    		<span class="month">Mar</span> 
    		<span class="year">2011</span>
    	</div>
    	<div class="datetime_mdash">-</div>
    	<div class="datetime">
    		<span class="day">7th</span> 
    		<span class="month">Feb</span> 
    		<span class="year">2011</span>
    	</div>
    	
    	<div class="place title">
    		<h4><a href="#" onclick="open_page('trips_place'); return false;">Trip title lorem ipsum</a></h4>
    		<a href="#" class="toggle_places open light">Hide places</a>
    	</div>
    	
    	<ol class="sub_trips">
    	
    		<li id="marker_id">
    		
    			<div class="datetime">
    				<span class="day">4th</span> 
    				<span class="month">Mar</span> 
    				<span class="year">2011</span>
    			</div>
    
    
    			<div class="place">		
	    			<h4><a href="#" onclick="open_page('trips_place'); return false;">Place, city, Country</a></h4>
    		
    				<ul class="meta">
    					<li class="icon thumb_up">Hitchability: Good</li>
    					<li class="icon time">Waiting time: 1h 4m</li>
    					<li class="icon comments">5 comments</li>
    				</ul>
    			</div>
    			    		
    		</li>
    	
    		<li id="marker_id">
    		
    			<div class="datetime">
    				<span class="day">7th</span> 
    				<span class="month">Mar</span> 
    				<span class="year">2011</span>
    			</div>
    		
    			<div class="place">		
	    			<h4><a href="#" onclick="open_page('trips_place'); return false;">Place, city, Country</a></h4>
    		
    				<ul class="meta">
    					<li class="icon thumb_up">Hitchability: Good</li>
    					<li class="icon time">Waiting time: 1h 4m</li>
    					<li class="icon comments">5 comments</li>
    				</ul>
    			</div>
    		
    			<div class="make_hitchplace">
    				<a href="#" class="yes_please png">Make place a hitchhiking spot</a>
    				<a href="#" class="no_thanks meta light"><i>No thanks</i></a>
    			</div>

    		</li>
    	</ol>

    </li>

</ol>



<!-- pagination --> 
<ul class="pagination">
    <li class="backwards"><span>&lsaquo;</span></li>
    <li class="num selected"><a href="#">1</a></li>
    <li class="num"><a href="#">2</a></li>
    <li class="num"><a href="#">3</a></li>
    <li class="num"><a href="#">4</a></li>
    <li class="num"><a href="#">5</a></li>
    <li>&bull;&bull;&bull;</li>
    <li class="num"><a href="#">20</a></li>

    <li class="forwards"><a href="#">&rsaquo;</a></li>

    <!-- timescale selector -->
    <li class="special timescale">
    	<label for="date_from_2" class="meta">From</label> <input type="text" class="meta" value="2.1.2010" size="10" name="date_from" id="date_from_2" style="text-align: center;" />
    	&nbsp;
    	<label for="date_to_2" class="meta">To</label> <input type="text" class="meta" value="2.1.2011" size="10" name="date_to" id="date_to_2" style="text-align: center;" />
    </li>	
    
    <!-- per page selector -->
    <li class="special perpage">
    	<select name="trips" id="trips_2" class="meta small">
    		<option value="10"><?php echo sprintf(_("%d per page"), 10); ?></option>
    		<option value="20"><?php echo sprintf(_("%d per page"), 20); ?></option>
    		<option value="50"><?php echo sprintf(_("%d per page"), 50); ?></option>
    		<option value="100"><?php echo sprintf(_("%d per page"), 100); ?></option>
    	</select>
    </li>
</ul>
<!-- /pagination -->

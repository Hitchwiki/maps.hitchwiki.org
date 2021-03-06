
<?= info_sign("This feature is under development and visible only for admins.",false); ?>


<h2><?php echo _("My trips"); ?></h2>

<a href="#"><b><?php echo _("My trips"); ?></b></a> &bull; 
<a href="#" onclick="open_page('trips_countries'); return false;"><?php echo _("Countries visited"); ?></a> &bull; 
<a href="#" onclick="open_page('trips_mountains'); return false;">Mountains</a> &bull; 
<a href="#" onclick="open_page('trips_import'); return false;"><?php echo _("Import"); ?></a> &bull; 


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
					
						<li id="marker_id" class="odd">
						
							<span class="datetime meta">24th February 2011</span>
							
							<ul class="place_info">
								<li class="location icon" style="background-image: url(static/gfx/flags/au.png);"><a href="#">City, Country</a></li>
							</ul>

						</li>
						
						
						
						<li id="marker_id" class="even">
						
							<span class="datetime meta">1st March 2011</span>
							
							<ul class="place_info">
								<li class="location icon" style="background-image: url(static/gfx/flags/au.png);"><a href="#">City, Country</a></li>
								<li class="meta align_left icon hitchability_3">Hitchability: Good</li>
								<li class="meta align_left icon time">Waiting time: 1h 4m</li>
							</ul>

						</li>
						
						
					
						<li id="marker_id" class="odd">
						
							<a href="#" class="make_hh_spot align_right smaller icon add" style="display:none;" onclick="init_add_place(); return false;">Make place a hitchhiking spot</a>
							
							<span class="datetime meta">24th March 2011</span>
							
							<ul class="place_info">
								<li class="location icon" style="background-image: url(static/gfx/flags/au.png);"><a href="#">City, Country</a></li>
							</ul>

						</li>
						
					
						<li id="marker_id" class="even">
						
							<a href="#" class="make_hh_spot align_right smaller icon add" style="display:none;" onclick="init_add_place(); return false;">Make place a hitchhiking spot</a>
							
							<span class="datetime meta">24th March 2011</span>
							
							<ul class="place_info">
								<li class="location icon" style="background-image: url(static/gfx/flags/au.png);"><a href="#">City, Country</a></li>
							</ul>

						</li>
						
					
						<li id="marker_id" class="odd">
						
							<a href="#" class="make_hh_spot align_right smaller icon add" style="display:none;" onclick="init_add_place(); return false;">Make place a hitchhiking spot</a>
							
							<span class="datetime meta">29th March 2011</span>
							
							<ul class="place_info">
								<li class="location icon" style="background-image: url(static/gfx/flags/au.png);"><a href="#">City, Country</a></li>
							</ul>

						</li>
					
						<li id="marker_id" class="even">
						
							<a href="#" class="make_hh_spot align_right smaller icon add" style="display:none;" onclick="init_add_place(); return false;">Make place a hitchhiking spot</a>
							
							<span class="datetime meta">22th April 2011</span>
							
							<ul class="place_info">
								<li class="location icon" style="background-image: url(static/gfx/flags/au.png);"><a href="#">City, Country</a></li>
							</ul>

						</li>


					</ol>
<script type="text/javascript">

$(".trips li").hover(
  function () {
    $(this).find(".make_hh_spot").show();
  }, 
  function () {
    $(this).find(".make_hh_spot").hide();
  }
);

</script>



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

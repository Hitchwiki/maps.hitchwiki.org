
<?= info_sign("This feature is under development and visible only for admins.",false); ?>


<h2><?php echo _("Countries visited"); ?></h2>

<a href="#" onclick="open_page('trips'); return false;"><?php echo _("My trips"); ?></a> &bull; 
<a href="#" onclick="open_page('trips_countries'); return false;"><b><?php echo _("Countries visited"); ?></b></a> &bull; 
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





					
					<ol class="trips countries_visited">
					
						<li id="marker_id" class="odd">
						
							<span class="datetime meta">January 2011</span>
							
							<ul class="place_info">
								<li class="location icon" style="background-image: url(static/gfx/flags/fi.png);"><a href="#">Finland</a></li>
								<li class="meta"><b>Places:</b> <a href="#">Helsinki</a>, <a href="#">Turku</a>, <a href="#">Tampere</a>, <a href="#">Jyväskylä</a></li>
							</ul>

						</li>
						
						
						<li id="marker_id" class="even">
						
							<span class="datetime meta">February 2011</span>
							
							<ul class="place_info">
								<li class="location icon" style="background-image: url(static/gfx/flags/fr.png);"><a href="#">France</a></li>
								<li class="meta"><b>Places:</b> <a href="#">Paris</a>, <a href="#">Marseille</a>, <a href="#">Lyon</a></li>
								
								<li class="location icon" style="background-image: url(static/gfx/flags/de.png);"><a href="#">Germany</a></li>
								<li class="meta"><b>Places:</b> <a href="#">Berlin</a>, <a href="#">Frankfurt</a></li>
								
								<li class="location icon" style="background-image: url(static/gfx/flags/lt.png);"><a href="#">Lithuania</a></li>
								
							</ul>

						</li>
						
						
						<li id="marker_id" class="odd">
						
							<span class="datetime meta">June 2011</span>
							
							<ul class="place_info">
								<li class="location icon" style="background-image: url(static/gfx/flags/de.png);"><a href="#">Germany</a></li>
							</ul>

						</li>
						
						
						<li id="marker_id" class="even">
						
							<span class="datetime meta">July 2011</span>
							
							<ul class="place_info">
								<li class="location icon" style="background-image: url(static/gfx/flags/lt.png);"><a href="#">Lithuania</a></li>
							</ul>

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

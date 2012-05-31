<h2><?php echo _("Statistics"); ?></h2>

<p><?php printf( _('There are currently %s places marked.'), '<b>'.total_places().'</b>' ); ?> <a href="<?= $settings["base_url"]; ?>/complete_statistics/" onclick="open_page('complete_statistics'); return false;"><?php echo _("See more complete statistics."); ?></a></p>


<div class="align_left" style="margin: 0 40px 20px 0;">

	<!-- top countries -->
	<h3 class="icon world"><?php printf( _( 'Top %s countries' ), "20" ); ?></h3>
	<table class="infotable" cellspacing="0" cellpadding="0">
		<thead>
			<tr>
				<th><?php echo _("Country"); ?></th>
				<th><?php echo _("Places"); ?></th>
			</tr>
		</thead>
		<tbody>
			<?php list_countries("tr", "markers", 20); ?>
		</tbody>
	</table>
	<!-- /top countries -->
	
</div>


<div class="align_left" style="margin: 0 40px 20px 0;">

	<!-- top cities -->
	<h3 class="icon building"><?php printf( _( 'Top %s cities' ), "20" ); ?></h3>
	<table class="infotable" cellspacing="0" cellpadding="0">
		<thead>
			<tr>
				<th><?php echo _("City"); ?></th>
				<th><?php echo _("Country"); ?></th>
				<th><?php echo _("Places"); ?></th>
			</tr>
		</thead>
		<tbody>
			<?php list_cities("tr", "markers", 20); ?>
		</tbody>
	</table>
	<!-- /top ities -->
	
</div>


<div class="align_left" style="margin: 0 40px 20px 0;">

	<!-- top continents -->
	<h3 class="icon world"><?php echo _( 'By continents' ); ?></h3>
	<table class="infotable" cellspacing="0" cellpadding="0">
		<thead>
			<tr>
				<th><?php echo _("Continent"); ?></th>
				<th><?php echo _("Places"); ?></th>
			</tr>
		</thead>
		<tbody>
			<?php list_continents("tr", true); ?>
		</tbody>
	</table>
	<!-- /top continents -->
	
	
	<!-- hitchability -->
	<h3 class="icon chart_bar"><?php echo _("Hitchability"); ?> - <?php echo _("Vote distribution"); ?></h3>
	<?php echo rating_chart_html(rating_stats()); ?>
	<p><?php
		$total = hitchability_votes_total();
		printf(ngettext("%d vote in total.", "%d votes in total.", $total), $total);
	?> <a href="<?= $settings["base_url"]; ?>/hitchability/" onclick="open_page('hitchability'); return false;"><?php echo _("Read more..."); ?></a></p>
	<!-- /hitchability -->
	
</div>

<div class="clear"></div>
	
<div style="margin: 0 0 20px 0;">

	<!-- highest places -->
	<h3><?php echo _("Highest hitchhiking places"); ?></h3>
	<table class="infotable" cellspacing="0" cellpadding="0" id="highest_places">
		<thead>
			<tr>
				<th><?php echo _("Country"); ?></th>
				<th><?php echo _("Highest place"); ?></th>
				<th><?php echo _("Average elevation"); ?></th>
				<th><?php echo _("Lowest place"); ?></th>
				<th><?php echo _("Places"); ?></th>
			</tr>
		</thead>
		<tbody>
		<?php
		
		$query = "SELECT 
						MAX(elevation) AS max, 
						AVG(elevation) AS avg, 
						MIN(elevation) AS min, 
						COUNT(id) as count,
						`elevation`,
						`country`,
						`locality`,
						`type` 
					FROM `t_points` 
					GROUP BY country
					ORDER BY max DESC";
		
		$result = mysql_query($query);
		$i=1;
		while ($row = mysql_fetch_array($result)) {
		
			$countryname = ISO_to_country($row["country"]);
			echo '<tr>';
			echo '<td><img class="flag" alt="'.$countryname.'" src="'.$settings["base_url"].'/static/gfx/flags/'.strtolower($row["country"]).'.png" /> <a href="./?q='.urlencode($countryname).'" id="search_for_this">'.$countryname.'</a></td>';
			echo '<td>'.$row["max"].' '._("m").'</td>';
			echo '<td>'.round($row["avg"]).' '._("m").'</td>';
			echo '<td>'.$row["min"].' '._("m").'</td>';
			echo '<td>'.$row["count"].'</td>';
			echo '</tr>';
			
			if($i>=10) break;
			else $i++;
		}
		?>
		</tbody>
	</table>
	
	<script type="text/javascript">
	$(function() {
	    
	    $("#highest_places .search_for_this").click(function(e){
	    	e.preventDefault();
	    	close_page();
	    	search($(this).text());
	    });
	
	});
	</script>
	<!-- /highest places -->

</div>


<?php /*
	<h3><?php printf( _( 'Top %s users' ), "20" ); ?></h3>
	<table class="infotable" cellspacing="0" cellpadding="0">
	    <thead>
	    	<tr>
	    		<th><?php echo _("User"); ?></th>
	    		<th><?php echo _("Places"); ?></th>
	    	</tr>
	    </thead>
	    <tbody>
	    	<tr>
	    		<td>-</td>
	    		<td>-</td>
	    	</tr>
	    </tbody>
	</table>
*/ ?>


<div class="clear"></div>

	<!-- place dencity -->
	<h3><?php echo _("Place density"); ?></h3>
	<!-- http://code.google.com/apis/visualization/documentation/gallery/geomap.html -->
	<iframe src="<?= $settings["base_url"]; ?>/ajax/map_statistics.php?map=3" width="820" height="430" border="0" style="border:0;"></iframe>
	<!-- /place dencity -->

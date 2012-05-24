
	<!-- Statistics -->
	<div data-role="page" id="statistics" data-title="Hitchwiki <?php echo _("Maps")." - "._("Statistics"); ?>">

		<div data-role="header" data-theme="e">
			<?= $ui_more_btn; ?>
			<h1><?php echo _("Statistics"); ?></h1>
		</div>
		
		<div data-role="content">
		
			<!-- hitchability -->
			<h4><?php echo _("Hitchability"); ?> - <?php echo _("Vote distribution"); ?></h4>
			<div class="ui-body ui-body-d"><?php echo rating_chart_html(rating_stats(), '100%', 'big'); ?></div>
			<p><?php
				$total = hitchability_votes_total();
				printf(ngettext("%d vote in total.", "%d votes in total.", $total), $total);
			?></p>
			<!-- /hitchability -->
		
			<p>
			<h4><?php printf( _( 'Top %s countries' ), "10" ); ?></h4>
			<span class="ui-li-count"><?php echo _("Places"); ?></span>
			<ul data-role="listview" data-inset="true">
				<?php 
					$list = list_countries("array", "markers", 10);
				
					foreach($list as $li) {
						echo '<li>';
						echo '<img src="'.$settings["base_url"].'/static/gfx/flags/'.strtolower($li["iso"]).'.png" alt="" class="ui-li-icon">';
						echo $li["name"];
						echo ' <span class="ui-li-count">'.$li["places"].'</span>';
						echo '</li>';
					}	
				?>
			</ul>
			</p>
			
			<p>
			<h4><?php printf( _( 'Top %s cities' ), "10" ); ?></h4>
			<ul data-role="listview" data-inset="true">
				
				<?php 
					$list = list_cities("array", "markers", 10);
				
					foreach($list as $li) {
						echo '<li>';
						echo '<img src="'.$settings["base_url"].'/static/gfx/flags/'.strtolower($li["country_iso"]).'.png" alt="" class="ui-li-icon">';
						echo $li["locality"].', '.$li["country_name"];
						echo ' <span class="ui-li-count">'.$li["places"].'</span>';
						echo '</li>';
					}	
				?>
			</ul>
			</p>

			<p>
			<h4><?php echo _( 'By continents' ); ?></h4>
			<ul data-role="listview" data-inset="true">		
				<?php 
					$list = list_continents("array", true);
				
					foreach($list as $li) {
						echo '<li>';
						echo $li["name"];
						echo ' <span class="ui-li-count">'.$li["places"].'</span>';
						echo '</li>';
					}	
				?>
			</ul>
			</p>
			
		</div><!-- /content -->
		
		<div data-role="footer" data-theme="e">
			<a href="./#more" data-icon="arrow-l" data-direction="reverse" data-role="button"><?php echo _("Back"); ?></a>
		</div>
		
	</div><!-- /page -->
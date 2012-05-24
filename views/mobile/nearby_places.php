
		<div data-role="header" data-theme="e">
			<?= $ui_home_btn; ?>
			<h1><?php echo _("Nearby places"); ?></h1>
		</div>
		
		<div data-role="content">
			
			<form>
			   <label for="km_slider">Kilometers:</label>
			   <input type="range" name="km_slider" id="km_slider" value="30" min="1" max="100" data-theme="e" />
			</form>

			<ul data-role="listview" data-inset="true" id="search_results"></ul> 

		</div><!-- /content -->

		<!-- footer -->
		<div data-role="footer" data-theme="e" data-id="search_footer" data-position="fixed">		
			<div data-role="navbar" data-iconpos="left">
				<ul>
					<li><a href="#searchpage" data-icon="search" data-transition="none"><?php echo _("Search"); ?></a></li>
					<li><a href="#browse_places" data-icon="search" data-transition="none"><?php echo _("Browse"); ?></a></li>
					<li><a href="#nearby_places" data-icon="locate" data-transition="none" class="ui-btn-active"><?php echo _("Nearby"); ?></a></li>
				</ul>
			</div><!-- /navbar -->
		</div><!-- /footer -->
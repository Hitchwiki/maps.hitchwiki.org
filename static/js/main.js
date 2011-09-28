/*
 * Hitchwiki Maps: main.js
 * Requires:
 * - jquery.js
 * - OpenLayers.js
 */


/*
 * Settings
 */
var debug = true; // enable / disable the log
var mapEventlisteners = false; // These will be turned on when page stops loading and map is ready

var proj4326 = new OpenLayers.Projection("EPSG:4326");
var projmerc = new OpenLayers.Projection("EPSG:900913");

// Missing tiles from the map
OpenLayers.Util.onImageLoadError = function(){this.src='static/gfx/openlayers/tile_not_found.gif';}
OpenLayers.Tile.Image.useBlankTile=false;

/*
 * When page loads
 */
$(document).ready(function() {

	// Initialize stuff when page has finished loading
	// --------------------------------------------------

	/*
	 * Debug log-box
	 */
	// Some positioning...
	log = $("#log").attr("style","position: absolute; top: 100px; left: 100px;");
	log_list = $("#log ol");
	log.draggable({handle: ".handle", containment: "body"});
	$("#log").resizable({alsoResize: '#log ol'});

	// Create a hide/show toggle button for the log window
	$("#log .close, .toggle_log").click(function(e){
	    e.preventDefault();
	    log.toggle();
	});
	
	// Show or hide log at the start?
	if(show_log==true) {
	    log.show();
	} else { 
	    log.hide();
	}

	// Log user's time
	var date = new Date();
	maps_debug("User's time "+date.getHours()+":"+date.getMinutes()+":"+date.getSeconds());


	// getUserLocation:
	if(private_location==false) { fetchlocation(); }


	// Remove JS-required alert	
	$("div#map").text('');


	// Load Map
	init_map();


	// Navigation
	$("a.pagelink").each(function(index) {
		$(this).click(function(e){
			e.preventDefault();
			open_page( this.id );
			$(this).blur();
		});
	});
	$("a.cardlink").each(function(index) {
		$(this).click(function(e){
			e.preventDefault();
			open_card( this.id, $(this).text() );
			$(this).blur();
		});
	});


	// Search form
	$("#search_form").submit(function(){ 
	    search($("#search_form input#q").val());
	    return false; 
	});

	// Autosuggest in search
	$("#search_form input#q").autocomplete({
	    source: function(request, response) {
	    	$.ajax({
	    		url: "http://ws.geonames.org/searchJSON",
	    		dataType: "jsonp",
	    		data: {
	    			featureClass: "P",
	    			style: "full",
	    			maxRows: 10,
	    			name_startsWith: request.term
	    		},
	    		success: function(data) {
	    			response($.map(data.geonames, function(item) {
	    				return {
	    					label: item.name + (item.adminName1 ? ", " + item.adminName1 : "") + ", " + item.countryName,
	    					value: item.name + (item.adminName1 ? ", " + item.adminName1 : "") + ", " + item.countryName
	    					//value: item.name + ", " + item.countryName
	    				}
	    			}))
	    		}
	    	})
	    },
	    minLength: 2,
	    select: function(event, ui) {
	    	search(ui.item.label);
	    },
	    open: function() {
	    	$(this).removeClass("ui-corner-all").addClass("ui-corner-top");
	    },
	    close: function() {
	    	$(this).removeClass("ui-corner-top").addClass("ui-corner-all");
	    }
	});
	
	
	    
	// Initialize page content area
	$("#pages .close").click(function(e){
		e.preventDefault();
		close_page();
	});
	if(open_page_at_start == false) {
	    $("#pages .page .content, #pages .page, #pages .close").hide();
	}
	
	$("#AddPlacePanel").hide();

	// Map selector
	$("#map_selector").show();
	
	$("#map_selector #selected_map").click(function(e){
		e.preventDefault();
		close_page();
		$("#map_selector #maplist").slideToggle('fast');
		$(this).blur();
	});
	$("#map_selector #maplist li a").click(function(e){
		e.preventDefault();
		$("#map_selector #maplist").slideToggle('fast');
		var thisLink = $(this);
		$("#map_selector #selected_map .map_name").text(thisLink.text());
		$("#map_selector #maplist li a").removeClass("selected");
		thisLink.addClass("selected");
		thisLink.blur();
	});
	
		
	
	// Add a place -panel
	$("#Navigation #add_place").click(function(e){
		e.preventDefault();
		init_add_place();
	});
	

	// Language Panel - Opening/closing
	$("#toggleLanguages, div#languagePanel h4 .close").click(function(e){
		e.preventDefault();
		stats("toggle_languagelist/");
		$(this).blur();
		$("div#languagePanel").toggle();
		//close_page();
	});
	$("div#languagePanel").attr("style","top: 10px; right: 10px;");


	// Tools Panel - Opening/closing
	$("#Footer #tools, div#toolsPanel h4 .close").click(function(e){
		e.preventDefault();
		stats("toggle_tools/");
		$(this).blur();
		$("div#toolsPanel").toggle();
	});


	// Tools Panel - make it draggable
	$(".floatingPanel.draggable")
		.draggable({ handle: 'h4' })
		.attr("style","text-align:left; top: 100px; left: 60px;");


	// Tools Panel - init zoom tool slider
	$("div#toolsPanel #zoom_slider").slider({
	    range: "max",
	    min: 0,
	    max: 18,
	    value: markersZoomLimit,
	    slide: function(event, ui) {
	    
	    		$("div#toolsPanel #zoom_slider_amount").text(ui.value);
	    		
	    		markersZoomLimit = ui.value;
	    		
	    		if(ui.value <= 6) {
	    			$("div#toolsPanel #zoomlevel *").hide();
	    			$("div#toolsPanel #zoomlevel .z_continent").show();
	    		}
	    		else if(ui.value <= 10) {
	    			$("div#toolsPanel #zoomlevel *").hide();
	    			$("div#toolsPanel #zoomlevel .z_country").show();
	    		}
	    		else if(ui.value <= 14) {
	    			$("div#toolsPanel #zoomlevel *").hide();
	    			$("div#toolsPanel #zoomlevel .z_city").show();
	    		}
	    		else {
	    			$("div#toolsPanel #zoomlevel *").hide();
	    			$("div#toolsPanel #zoomlevel .z_streets").show();
	    		}
	    		
	    		$.cookie(cookie_prefix+'markersZoomLimit', ui.value, { path: '/', expires: 666 });

	    		refreshMapMarkers();
	    }
	});
	
	$("div#toolsPanel #zoom_slider_amount").text($("#toolsPanel #zoom_slider").slider("value"));
	
	// Tools Panel and loading animation - hide at the beginning
	$("div#toolsPanel, #loading-bar").hide();
	
	var sidebar_height = $("#Sidebar").height();
	$("div#map").attr("style","min-height: "+sidebar_height+"px");


	// Refresh login session
	// Keep Hitchwiki user session fresh by refreshing an iframe with hitchwiki-page in it
	// Otherwice it'll just dissapear and Maps cannot reach it anymore, even user would be logged in
	function loginRefreshAreas() {
	    
	    $.ajax({
	      url: "ajax/header_login.php",
	      cache: false,
	      success: function(content){
		$("#loginRefreshArea").html(content);
	        maps_debug("Session Refresh: refreshed login area.");
	      }
	    });
	    
	    $.ajax({
	      url: "ajax/header_navi.php",
	      cache: false,
	      success: function(content){
		$("#Navigation2").html(content);
	        maps_debug("Session Refresh: refreshed navi area.");
	      }
	    });
	}

	var loginRefresh = $("iframe#loginRefresh");
	window.setInterval(function(){
		var date = new Date();
		loginRefresh.attr("src","http://hitchwiki.org/en/index.php?title=Maps.hitchwiki.org&redirect=no&action=render&ctype=text/plain&hitchwiki_maps_session_refresh");
		maps_debug("Session Refresh: session refreshed in iframe @ "+date.getHours()+":"+date.getMinutes()+":"+date.getSeconds());
		
	}, 300000); // run every 5mins = 300000 milliseconds
	
	// Refresh some views on the page after iframe has finished loading
	loginRefresh.load(function (){
	    loginRefreshAreas();   
	});
	
	loginRefreshAreas();
});



/*
 * Initialize map
 */
var map, places, map_center;
var handle_add_place_click = false;


function init_map() {
	maps_debug("Initialize the map");

	// Custom images from our own server
	OpenLayers.ImgPath = "static/gfx/openlayers/";
	
	// Create map with controls	
	map = new OpenLayers.Map('map', {
	/* OLD:
		projection: proj4326,
		displayProjection: proj4326,
		eventListeners: {
			"move": mapEventMoveStarted,
		    "moveend": mapEventMove,
		    "zoomend": mapEventZoom,
		    "changelayer": mapLayerChanged,
		    "changebaselayer": mapBaseLayerChanged
		},
	    numZoomLevels: 19,
	NEW: */
		
		projection: proj4326,
		displayProjection: projmerc,
		units: "m",
		numZoomLevels: 18,
		maxResolution: 156543.0339,
		maxExtent: new OpenLayers.Bounds(-20037508, -20037508, 20037508, 20037508.34),
		
		eventListeners: {
			"move": mapEventMoveStarted,
		    "moveend": mapEventMove,
		    "zoomend": mapEventZoom,
		    "changelayer": mapLayerChanged,
		    "changebaselayer": mapBaseLayerChanged
		},
		
	    controls: [
	        new OpenLayers.Control.Navigation(),
	        new OpenLayers.Control.PanZoomBar(),
	        new OpenLayers.Control.ScaleLine(),
	        //new OpenLayers.Control.LayerSwitcher({'ascending':false}),
	        //new OpenLayers.Control.Permalink('permalink'),
	        //new OpenLayers.Control.Permalink(),
	        //new OpenLayers.Control.KeyboardDefaults(),
	        //new OpenLayers.Control.MousePosition(),
	        new OpenLayers.Control.OverviewMap()
	        
	        
	    ]
	    
	});
	
 	
	// Measure controls
	// http://openlayers.org/dev/examples/measure.html
	
	// style the sketch fancy
	var sketchSymbolizers = {
	    "Point": {
	        pointRadius: 4,
	        graphicName: "square",
	        fillColor: "white",
	        fillOpacity: 1,
	        strokeWidth: 1,
	        strokeOpacity: 1,
	        strokeColor: "#db7700"
	    },
	    "Line": {
	        strokeWidth: 3,
	        strokeOpacity: 1,
	        strokeColor: "#333",
	        strokeDashstyle: "dash"
	    },
	    "Polygon": {
	        strokeWidth: 2,
	        strokeOpacity: 1,
	        strokeColor: "#333",
	        fillColor: "white",
	        fillOpacity: 0.3
	    }
	};
	var style = new OpenLayers.Style();
	style.addRules([
	    new OpenLayers.Rule({symbolizer: sketchSymbolizers})
	]);
	var styleMap = new OpenLayers.StyleMap({"default": style});
	
	measureControls = {
	    line: new OpenLayers.Control.Measure(
	        OpenLayers.Handler.Path, {
	            persist: true,
	            handlerOptions: {
	                layerOptions: {styleMap: styleMap}
	            }
	        }
	    ),
	    polygon: new OpenLayers.Control.Measure(
	        OpenLayers.Handler.Polygon, {
	            persist: true,
	            handlerOptions: {
	                layerOptions: {styleMap: styleMap}
	            }
	        }
	    )
	};
	var control;
	for(var key in measureControls) {
	    control = measureControls[key];
        control.geodesic = true;//take this away if you want to make geodesic optional
	    control.events.on({
	        "measure": handleMeasurements,
	        "measurepartial": handleMeasurements
	    });
	    map.addControl(control);
	}
	
	document.getElementById('noneToggle').checked = true;


 	// Different colors for markers depending on their rating
	var colors = [	
					"#ffffff", // rate 0 (white)
					"#00ad00", // rate 1 (green)
					"#96ad00", // rate 2
					"#ffff00", // rate 3
					"#ff8d00", // rate 4
					"#ff0000"  // rate 5 (red)
				];
	
	// Get rating from marker
	var markerContext = {
	    getColor: function(feature) {
	        return colors[feature.attributes["rating"]];
	    }/*,
	    radius: function(feature) { 
	    	return Math.min(feature.attributes.count, 7) + 3;
	    }*/
	};
	
	// Initialize a layer for the places
	// You can fill it with refreshMapMarkers() using listener events
	places = new OpenLayers.Layer.Vector(
		"Places", {/*
				strategies: [
				    new OpenLayers.Strategy.Fixed(),
				    new OpenLayers.Strategy.Cluster()
				],*/
				styleMap: new OpenLayers.StyleMap({
                	"default": new OpenLayers.Style({
                	
    				    graphicZIndex: 1,
					    pointRadius: 5,//"${radius}",
    				    strokeWidth: 2,
						cursor: "pointer",
                	    fillColor: "#000000",//#ffcc66
					    strokeColor: "${getColor}" // using context.getColor(feature)
					    
					}, {context: markerContext}),
                	"select": new OpenLayers.Style({
                	
                	    graphicZIndex: 2,
                	    fillColor: "#66ccff",
                	    strokeColor: "#3399ff"
                	    
                	}),
                	"hover": new OpenLayers.Style({
                	
                	    graphicZIndex: 2,
                	    fillColor: "#3399ff"
                	    
                	})
                }), //stylemap end

			isBaseLayer: false,
			rendererOptions: {yOrdering: true}
        }
	);//places end
	
  
	// Event listeners for places layer
	places.events.on({
		'featureselected': function(event) {
			feature = event.feature;
			maps_debug("Selected marker "+feature.attributes.id);
			showPlacePanel(feature.attributes.id);
                
		},
		'featureunselected': function(feature) {
			maps_debug("Unselected marker.");
			hidePlacePanel();
		}
	});


	// Layer for the places count
	places_count = new OpenLayers.Layer.Vector(
		"Places count",
		{
			styleMap: new OpenLayers.StyleMap({

				fillOpacity: 1, 
				fillColor: "#fde669", 
				strokeColor: "#c38b06", 
    			strokeWidth: 1,
				pointRadius: "${radius}",
				cursor: "pointer",
								
				label: "${places}",
				fontColor: "#824300",
				fontSize: "10px",
				fontFamily: "'Trebuchet MS',Arial,sans-serif",
				fontWeight: "bold",
				labelAlign: "cm"
			}),
			isBaseLayer: false,
			rendererOptions: {yOrdering: true}
		}
	);

  

	/*
	 * Create base layer for new place
	 */
	add_place_target = new OpenLayers.Layer.Vector(
		"New place",
		{
			styleMap: new OpenLayers.StyleMap({
				"default": new OpenLayers.Style({
	    	    	cursor: "move",
        	    	graphicZIndex: 3,
	    	    	pointRadius: 7,
        	    	strokeWidth: 5,
	    	    	strokeColor: "#f57900",
        	    	fillColor: "#f57900", 
        	    	fillOpacity: 0
        	    	//stroke: false
				    
				}),
				"hover": new OpenLayers.Style({
	    	    	strokeColor: "#ff9834"
				})
			}), //stylemap end
			
			isBaseLayer: false
		}
	);
	var hover_new_place = new OpenLayers.Control.SelectFeature(add_place_target, {
	    hover: true,
	    highlightOnly: true,
	    renderIntent: "hover"
	});
	map.addControl(hover_new_place);
	hover_new_place.activate();
	

	/*
	 * Map layers
	 * Control loading of these from config.php
	 * OSM will be always loaded and used as a default
	 */
	 
	
	// OSM layer
	var mapnik = new OpenLayers.Layer.OSM();
	
	// OSM layer 2
	var osmarender = new OpenLayers.Layer.OSM(
	    "OpenStreetMap (Tiles@Home)",
	    "http://tah.openstreetmap.org/Tiles/tile/${z}/${x}/${y}.png"
	);

	// Google layers
	if(layer_google == true) {
	
		var gphy = new OpenLayers.Layer.Google(
		    "Google Physical",
		    {
		    	visibility: false, 
		    	sphericalMercator: true, 
		    	type: G_PHYSICAL_MAP
		    }
		);
		var gmap = new OpenLayers.Layer.Google(
		    "Google Streets",
		    {
		    	visibility: false, 
		    	sphericalMercator: true, 
		    	numZoomLevels: 20
		    }
		);
		var ghyb = new OpenLayers.Layer.Google(
		    "Google Hybrid",
		    {
		    	visibility: false, 
		    	sphericalMercator: true, 
		    	type: G_HYBRID_MAP, 
		    	numZoomLevels: 20
		    }
		);
		var gsat = new OpenLayers.Layer.Google(
		    "Google Satellite",
		    {
		    	visibility: false, 
		    	sphericalMercator: true, 
		    	type: G_SATELLITE_MAP, 
		    	numZoomLevels: 22
		    }
		);
	}

	// create Yahoo layer
	if(layer_yahoo == true) {
	
		var yahoo = new OpenLayers.Layer.Yahoo(
		    "Yahoo Street",
		    {
		    	visibility: false, 
		    	sphericalMercator: true
		    }
		);
		var yahoosat = new OpenLayers.Layer.Yahoo(
		    "Yahoo Satellite",
		    {
		    	visibility: false, 
		    	type: YAHOO_MAP_SAT, 
		    	sphericalMercator: true
		    }
		);
		var yahoohyb = new OpenLayers.Layer.Yahoo(
		    "Yahoo Hybrid",
		    {
		    	visibility: false, 
		    	type: YAHOO_MAP_HYB, 
		    	sphericalMercator: true
		    }
		);
		
	}
	
	// create Virtual Earth layers
	if(layer_vearth == true) {
	
		var veroad = new OpenLayers.Layer.VirtualEarth(
		    "Virtual Earth Roads",
		    {
		    	visibility: false, 
		    	type: VEMapStyle.Road, 
		    	sphericalMercator: true
		    }
		);
		var veaer = new OpenLayers.Layer.VirtualEarth(
		    "Virtual Earth Aerial",
		    {
		    	visibility: false, 
		    	type: VEMapStyle.Aerial, 
		    	sphericalMercator: true
		    }
		);
		var vehyb = new OpenLayers.Layer.VirtualEarth(
		    "Virtual Earth Hybrid",
		    {
		    	visibility: false, 
		    	type: VEMapStyle.Hybrid, 
		    	sphericalMercator: true
		    }
		);
		
	}
	 
                
	/*
	 * Add produced layers to the map
	 */
    if(layer_google == true) {map.addLayers([gphy, gmap, ghyb, gsat]); }
    if(layer_yahoo == true) {map.addLayers([yahoo, yahoosat, yahoohyb]); }
    if(layer_vearth == true) {map.addLayers([veroad, veaer, vehyb]); }
    
	map.addLayers([
        mapnik, osmarender,
        
		places,
		places_count,
		add_place_target
	]);
		
	add_place_target.setVisibility(false);
		
	/*
	 * Set requested layer active
	 */
	if(layer_default == "mapnik") { map.setBaseLayer(mapnik); }
	else if(layer_default == "osmarender") { map.setBaseLayer(osmarender); }
	
	// Google
	else if(layer_default == "gphy" && layer_google == true) { map.setBaseLayer(gphy); }
	else if(layer_default == "gmap" && layer_google == true) { map.setBaseLayer(gmap); }
	else if(layer_default == "ghyb" && layer_google == true) { map.setBaseLayer(ghyb); }
	else if(layer_default == "gsat" && layer_google == true) { map.setBaseLayer(gsat); }
	
	// Yahoo
	else if(layer_default == "yahoo" && layer_yahoo == true) { map.setBaseLayer(yahoo); }
	else if(layer_default == "yahoosat" && layer_yahoo == true) { map.setBaseLayer(yahoosat); }
	else if(layer_default == "yahoohyb" && layer_yahoo == true) { map.setBaseLayer(yahoohyb); }
	
	// Virtual Earth
	else if(layer_default == "veroad" && layer_vearth == true) { map.setBaseLayer(veroad); }
	else if(layer_default == "veaer" && layer_vearth == true) { map.setBaseLayer(veaer); }
	else if(layer_default == "vehyb" && layer_vearth == true) { map.setBaseLayer(vehyb); }
	
	
	/*
	 * Map selecting from the map selector
	 */
	// osm
	$("#map_selector #maplist li a[name='mapnik']").click(function(e){ e.preventDefault(); map.setBaseLayer(mapnik); stats("map_layer/osm/mapnik"); });
	$("#map_selector #maplist li a[name='osmarender']").click(function(e){ e.preventDefault(); map.setBaseLayer(osmarender); stats("map_layer/osm/osmarender"); });
	
	// google
	if(layer_google == true) {
		$("#map_selector #maplist li a[name='gphy']").click(function(e){ e.preventDefault(); map.setBaseLayer(gphy); stats("map_layer/google/gphy"); });
		$("#map_selector #maplist li a[name='gmap']").click(function(e){ e.preventDefault(); map.setBaseLayer(gmap); stats("map_layer/google/gmap"); });
		$("#map_selector #maplist li a[name='ghyb']").click(function(e){ e.preventDefault(); map.setBaseLayer(ghyb); stats("map_layer/google/ghyb"); });
		$("#map_selector #maplist li a[name='gsat']").click(function(e){ e.preventDefault(); map.setBaseLayer(gsat); stats("map_layer/google/gsat"); });
	}
	
	// yahoo
	if(layer_yahoo == true) {
		$("#map_selector #maplist li a[name='yahoo']").click(function(e){ e.preventDefault(); map.setBaseLayer(yahoo); stats("map_layer/yahoo/yahoo"); });
		$("#map_selector #maplist li a[name='yahoosat']").click(function(e){ e.preventDefault(); map.setBaseLayer(yahoosat); stats("map_layer/yahoo/yahoosat"); });
		$("#map_selector #maplist li a[name='yahoohyb']").click(function(e){ e.preventDefault(); map.setBaseLayer(yahoohyb); stats("map_layer/yahoo/yahoohyb"); });
	}
	
	// virtual earth
	if(layer_vearth == true) {
		$("#map_selector #maplist li a[name='veroad']").click(function(e){ e.preventDefault(); map.setBaseLayer(veroad); stats("map_layer/vearth/veroad"); });
		$("#map_selector #maplist li a[name='veaer']").click(function(e){ e.preventDefault(); map.setBaseLayer(veaer); stats("map_layer/vearth/veaer"); });
		$("#map_selector #maplist li a[name='vehyb']").click(function(e){ e.preventDefault(); map.setBaseLayer(vehyb); stats("map_layer/vearth/vehyb"); });
	}
	
	
	/*
	 * Hovering place markers
	 */
	var hover_marker = new OpenLayers.Control.SelectFeature(places, {
	    hover: true,
	    highlightOnly: true,
	    renderIntent: "hover"
	});
	map.addControl(hover_marker);
	hover_marker.activate();


	
	/*
	 * Selecting markers
	 */
	var select_marker = new OpenLayers.Control.SelectFeature(places, 
							{
								hover: false,
								highlightOnly: true,
								clickout: true,
								multiple: false,
								box: false
							});
    map.addControl(select_marker);
    select_marker.activate();



	/*
	 * Get labels to the map
	 */
	markerCountLabels();

	// Selecting labels
	var select_countrydot = new OpenLayers.Control.SelectFeature(places_count, 
							{
								onSelect: onCountrydotSelect, 
								onUnselect: onCountrydotUnselect,
								hover: true,
								clickout: true,
								multiple: false,
								box: false
							});
    map.addControl(select_countrydot);
    select_countrydot.activate();


	/*
	 * add and expand the overview map control
	 */
	var overview = new OpenLayers.Control.OverviewMap();
	map.addControl(overview);
	overview.maximizeControl();


	/*
	 * Hide panel where we show info about place
	 */
	$("#PlacePanel").hide();

	
	/*
	 * Set map
	 * You can set these by $_GET[lat/lon/zoom] - see index.php for more
	 */
	// Map position
    map.setCenter(new OpenLayers.LonLat(lon, lat).transform(proj4326, projmerc));
    
    // Zoom
    if(zoom==false) { map.zoomToMaxExtent(); }
    else { map.zoomTo(zoom); }
   
   	// Let eventlisteners be free! :-)
	// Meaning, they can be called from now on that page has stopped loading
	mapEventlisteners = true;


} // init_map end



/*
 * Open small countryinfo-popup when selecting count labels
 */
/*
var selectControl, selectedFeature;
function onCountrydotPopupClose(evt) {
    selectControl.unselect(selectedFeature);
}
*/
function onCountrydotSelect(feature) {
	var point = feature.geometry.getBounds().getCenterLonLat();

    if(point.lat > map_center.lat) {
    	var lat_offset = 5;
    } else {
    	var lat_offset = -5;
    }
    if(point.lon > map_center.lon) {
    	var lon_offset = -5;
    } else {
    	var lon_offset = 5;
    }
    
    
    popup = new OpenLayers.Popup.FramedCloud("Country", 
		point,
		null,
		'<div style="color: #111;"><h4 style="margin:0; padding: 0 0 3px 21px; background: url(static/gfx/flags/'+feature.attributes.iso.toLowerCase()+'.png) no-repeat 0 3px;">' + feature.attributes.name +'</h4><small class="grey">' + feature.attributes.places +' '+_("places")+'.<br /><i>'+_("Zoom closer to see them.")+'</i></small></div>',
		{
			'size': new OpenLayers.Size(15,15), 
			'offset': new OpenLayers.Pixel(lon_offset,lat_offset)
		}, 
		false);//, onCountrydotPopupClose);
		
	feature.popup = popup;
	map.addPopup(popup);
}
function onCountrydotUnselect(feature) {
    map.removePopup(feature.popup);
    feature.popup.destroy();
    feature.popup = null;
} 


/*
 * Measure controls
 * http://openlayers.org/dev/examples/measure.html
 */
function handleMeasurements(event) {
    var geometry = event.geometry;
    var units = event.units;
    var order = event.order;
    var measure = event.measure;
    var element = document.getElementById('toolOutput');
    var out = "";
    if(order == 1) {
        out += measure.toFixed(3) + " " + units;
    } else {
        out += measure.toFixed(3) + " " + units + "<sup>2</" + "sup>";
    }
    element.innerHTML = out;
}

function toggleControl(element) {
    for(key in measureControls) {
        var control = measureControls[key];
        if(element.value == key && element.checked) {
            control.activate();
        } else {
            control.deactivate();
        }
    }
}
/* Hidden since geodesic is true by default, but if you want to make it optional, use this (and check HTML from index.php)
function toggleGeodesic(element) {
    for(key in measureControls) {
        var control = measureControls[key];
        control.geodesic = element.checked;
    }
}
*/





/*
 * Get users current location by either W3 geolocation API (if browser supports) or query IP-location database
 */
function fetchlocation() {
	// Test that the browser supports the GeoLocation object
	if (navigator.geolocation)
	{
	   maps_debug("Browser supports Geolocation. Asking to use it...");
	   
	   // Callback fetchlocationW3() if success, on failure go for fetchlocationByIP()
	   navigator.geolocation.getCurrentPosition( fetchlocationW3, fetchlocationByIP );
	}
	// If not, use our own fetchlocationByIP -service
	else
	{
	   maps_debug("Browser didn't support geolocation. Using our own IP-based service.");
	   fetchlocationByIP();
	}
}


/*
 * Display users location in webpage
 *
 * Eats JSON like this (we use Latitude, Longitude, City, State, RegionName and CountryName, Status -values):
{
  "Ip" : "76.121.45.200",
  "Status" : "OK",
  "CountryCode" : "US",
  "CountryName" : "United States",
  "RegionCode" : "53",
  "RegionName" : "Washington",
  "City" : "Bellingham",
  "ZipPostalCode" : "98226",
  "Latitude" : "48.7982",
  "Longitude" : "-122.41"
}
 */
function displaylocation(location) {
	if (location.Status == 'OK') {
		maps_debug("Showing location under search bar: "+location.City+", "+location.CountryName);
  		// Tool is hidden as a default, and stays hidden if no location is found
		var show_nearby = false;
		
		// City
		if(location.City != '' || location.City != 'undefined' || location.City != undefined) { 
			$('#nearby .locality a')
				.text(location.City + ', ')
				.click(function(){ search(location.City + ', ' + location.CountryName); });
			$('#nearby .locality').show('fast');
			show_nearby = true;
		}
		/*
		// State / Region
		if(location.State != '--') {
			$('#nearby .state a')
				.text(location.State)
				.click(function(){ search(location.State + ', ' + location.CountryName); });
			$('#nearby .state').show('fast');
			show_nearby = true;
		}
		else if(location.RegionName != '') {
			$('#nearby .state a')
				.text(location.RegionName)
				.click(function(){ search(location.RegionName + ', ' + location.CountryName); });
			$('#nearby .state').show('fast');
			show_nearby = true;
		}
		*/
		// Country
		if(location.CountryName != '' || location.CountryName != 'undefined' || location.CountryName != undefined) { 
			$('#nearby .country a')
				.text(location.CountryName)
				.click(function(){ search(location.CountryName); });
			$('#nearby .country').show('fast');
			show_nearby = true;
			
		}
		
		// Get info for logging
		if(location.CountryCode != '' || location.CountryCode != undefined) var log_country = '"'+location.CountryCode+'"';
		else var log_country = false;
		
		if(location.City != '' || location.City != undefined) var log_city = '"'+location.City+'"';
		else var log_city = false;
		
		
		// Show tool if content is filled
		if(show_nearby == true) { $('#nearby').slideDown('fast'); }
		else { $('#nearby').hide(); }
		
		
		if(location.Latitude != '' && location.Longitude != '') {
			maps_log("visit_location", '{"country":'+log_city+',"country":'+log_country+',"lat":"'+location.Latitude+'","lon":"'+location.Longitude+'"}');
		}
		
		// Move map to the location
		/*
		if(location.Latitude != '' && location.Longitude != '') {
			map_debug("Centering map to the point "+location.Latitude+", "+location.Longitude);
			zoomMapIn(location.Latitude, location.Longitude, 5);
		}
		*/
    
	}
}




/*
 * Browsers native Geolocation API
 * http://dev.w3.org/geo/api/spec-source.html
 */
function fetchlocationW3(position) {
	
	maps_debug("Got location from browser. Sending it to the geocoder.");
	
	// Reverse Geocode latlon -> address
	$.getJSON('ajax/geocoder.php?mode=reverse&q=' + position.coords.latitude + ',' + position.coords.longitude, function(data) {			

			if(data.error==true) {
				maps_debug("Error when trying to get reverce geocode. Using our own IP-geolocation service");
				fetchlocationByIP();
			}
			else {
				maps_debug("Geocoded address succesfully.");
				
				var location = {
					"Status" : "OK",
					"Latitude" : position.coords.longitude,
					"Longitude" : position.coords.latitude,
					"CountryCode" : data.country_code,
					"CountryName" : data.country_name,
					"RegionName" : "",
					"State" : "--",
					"City" : data.locality,
					"ZipPostalCode" : data.postcode
				};
				
				displaylocation(location);
			
			}
	});
}



/* Get User Location by current IP
 * http://there4development.com/2010/03/geolocation-services-with-jquery-and-ipinfodb/
 * Requires:
 * - jQuery
 * - jQuery JSON
 * - jQuery Cookie
 * - Snoopy PHP
 */
fetchlocationByIP = function() {
   maps_debug("Using IP-based geolocation service.");
   
  // look in the cookie for the location data
  cookiedata = $.cookie(geolocation_cookiename);
  if ('' != cookiedata) {
    locationinfo = $.evalJSON(cookiedata);
    if ((locationinfo != null) && (locationinfo.IP == ip)) {
      displaylocation(locationinfo);
      $.cookie(geolocation_cookiename, cookiedata, geolocation_cookieoptions);
      return;
    }
  }
  // it's not in the cookie, so fetch from the server
  $.getJSON(
    geolocation, {
      'timezone' : 'false', // set this to false to save the service 2 queries
      'ip'       : ip
    },
    function(data) {
      data.IP = ip;
      displaylocation(data);
      cookiedata = $.toJSON(data);
      $.cookie(geolocation_cookiename, cookiedata, geolocation_cookieoptions);
    }
  );
}





/*
 * Call when moving ends
 */
function mapEventMove() {
	if(mapEventlisteners==true) {
		//maps_debug("map movement ended");
		
		// Refresh markers in viewport
		refreshMapMarkers();
		
	}
}


/*
 * Call when moving starts
 */
function mapEventMoveStarted() {

	var currentZoom = map.getZoom();

	// Hide markers layer if zoom level isn't deep enough, and show marker count-labels instead
	if(currentZoom < markersZoomLimit) {
		places.display(false);
	}
	else {
		places.display(true);
	}
	
}


/*
 * Call when zooming ends
 */
function mapEventZoom() {
	if(mapEventlisteners==true) {
		maps_debug("Map Zoom: "+map.getZoom());
		
		// This gets called anyway, because when zooming, then also moving
		//refreshMapMarkers();
	}
}


/*
 * Call when changing map layer
 */
function mapLayerChanged() {
	if(mapEventlisteners==true) {
		maps_debug("map layer changed");
		//alert("event listener: mapLayerChanged");
	
	}
}


/*
 * Call when changing map base layer
 */
function mapBaseLayerChanged() {
	if(mapEventlisteners==true) {
		maps_debug("map baselayer changed");
		//alert("event listener: mapBaseLayerChanged");


	}
}


/*
 * Add marker count labels to the map
 */

function markerCountLabels() {
	maps_debug("Gathering marker count labels from the API...");
	
	// Get labels from the database
	// Gets only countries with 1+ places
	
	var apiCall = 'api/?countries&coordinates';	
	maps_debug("Calling API: "+apiCall);
		
	$.getJSON(apiCall, function(data) {
		
		maps_debug("Got labels by JSON. Starting to loop 'em.");
	
		// Got labels, build up markers
	    var labelStock = [];

	    $.each(data, function(key, value) {
			
			//maps_debug("Label: "+value.name+" | "+value.lon+", "+value.lat);

			if(value.lon != "" || value.lat != "" || value.lon != undefined || value.lat != undefined) {
			
				// This value is used to make bigger background dot for bigger values, so all the numbers can fit in
	    		if(value.places >= 1000) var pointRadius = 14;
	    		else if(value.places >= 100) var pointRadius = 12;
	    		else if(value.places >= 10) var pointRadius = 9;
	    		else var pointRadius = 7;
				
	    		var coords = new OpenLayers.LonLat(value.lon, value.lat).transform(proj4326, map.getProjectionObject());
				labelStock.push(
					new OpenLayers.Feature.Vector(
						new OpenLayers.Geometry.Point(coords.lon, coords.lat),
						{
							name: value.name,
							places: value.places,
							iso: value.iso,
							radius: pointRadius
						}
					)
				);
				
			} else {
				maps_debug("Lat/Lon missing for the label: "+value.name+" ("+value.lat+", "+value.lon+")");
			}
	    }); // each end

		// Add array of markers to the map
		if(labelStock.length > 0) {
		    maps_debug("Adding "+labelStock.length+" labels to the map.");
		    places_count.addFeatures(labelStock);
		} else {
		    maps_debug("Error: didn't get any labels to add.");
		}
	}); // get json end
}


/*
 * Our own little markermanager
 * Shows only what's needed, not all the world at the same time. ;-)
 */
var markers = new Array();
function refreshMapMarkers() {
	
	var currentZoom = map.getZoom();
	map_center = map.getCenter();

	// Hide markers layer if zoom level isn't deep enough, and show marker count-labels instead
	if(currentZoom < markersZoomLimit) {
		places.setVisibility(false);
		places_count.setVisibility(true);
	}
	else {
		places.setVisibility(true);
		places_count.setVisibility(false);
	}
	
	
	// Start loading markers only after certain zoom level
	if(currentZoom >= markersZoomLimit) {

		// Get corner coordinates from the map
		var extent = map.getExtent();
		var corner1 = new OpenLayers.LonLat(extent.left, extent.top).transform(projmerc, proj4326);
		var corner2 = new OpenLayers.LonLat(extent.right, extent.bottom).transform(projmerc, proj4326);

		var apiCall = 'api/?bounds='+corner2.lat+','+corner1.lat+','+corner1.lon+','+corner2.lon;	
		maps_debug("Calling API: "+apiCall);
	
		// Get markers from the API for this area
		$.getJSON(apiCall, function(data) {
			// Go trough all markers
			
			maps_debug("Starting markers each-loop...");
			
			// Loop markers we got trough 
	        var markerStock = [];
			$.each(data, function(key, value) {
			/* Value includes:
			    value.id; 
			    value.lat;
			    value.lon;
			    value.rating;
			*/
			
				// Check if marker isn't already on the map
				// and add it to the map
				if(markers[value.id] != true) {
					markers[value.id] = true;
					
					//maps_debug("Adding marker #"+value.id +"<br />("+value.lon+", "+value.lat+")...");
					
	                var coords = new OpenLayers.LonLat(value.lon, value.lat).transform(proj4326,projmerc);
	                
	                markerStock.push(
	                    new OpenLayers.Feature.Vector(
	                        new OpenLayers.Geometry.Point(coords.lon, coords.lat),
							{
								id: value.id,
								rating: value.rating
							}
	                    )
	                );
	                
	                
	                //maps_debug("...done.");
	
				} 
				else {
					//maps_debug("marker #"+value.id +" already on the map.");
				}
				
			// each * end
			});
			
			if(markerStock.length > 0) {
				maps_debug("Loop ended. Adding "+markerStock.length+" new markers to the map.");
		        places.addFeatures(markerStock);
			} else {
				maps_debug("Loop ended. No new markers found from this area.");
			}	
		// getjson * end
		});
	
	
		
	// end zoom limit
	}
}


/*
 * Initialize add new place
 */
var add_place_initialized_once = false;
var add_place_open = false;
function init_add_place(prefill) {
	maps_debug("Initialize adding a new place");
	
	stats("add_place/");
	
	
	// Hides possibly open place panel
	$("#map").click();

	// Inform that we are open now
	add_place_open = true;
	
	// Get panel contents
	$.ajax({
		url: "ajax/add_place.php",
		async: false,
		success: function(content){ 

			$("#PlacePanel").html(content).show();

			// Shring map a bit and make some space for the panel
			$("#map").attr("style","right:250px;");
			
			
			// Start listening single clicks
			handle_add_place_click = true;
			
			// Add target to the center of the map
			
			add_place_target.setVisibility(true);
			    
			if(add_place_initialized_once==false) {
			    maps_debug("Adding layers for new place.");
			    
			    
			    // Create a dot for new place
			    var new_place = new OpenLayers.Feature.Vector( new OpenLayers.Geometry.Point(map.getCenter().lon, map.getCenter().lat) );
			    add_place_target.addFeatures(new_place);
			    
			    var new_place_lon = new_place.geometry.x; 
			    var new_place_lat = new_place.geometry.y;
			    update_add_place(new_place_lon, new_place_lat, true);
			    
			
			    // Add dot dragging
			    var add_place_drag = new OpenLayers.Control.DragFeature(add_place_target, {
			        onComplete: function(feature) { 
			        
			            	var lat = feature.geometry.y;
			        		var lon = feature.geometry.x;
			        		
			        		new_place.move(new OpenLayers.LonLat(lon, lat));
			        		update_add_place(lon, lat, true);
			        		maps_debug("Add marker moved (move): "+lat+", "+lon);
			        }
			    });
			    map.addControl(add_place_drag);
			    add_place_drag.activate();
			    
			
			    // Click Handler
			    OpenLayers.Control.Click = OpenLayers.Class(OpenLayers.Control, {                
			           defaultHandlerOptions: {
			               'single': true,
			               'double': false,
			               'pixelTolerance': 0,
			               'stopSingle': false,
			               'stopDouble': false
			           },
			    
			           initialize: function(options) {
			               this.handlerOptions = OpenLayers.Util.extend(
			                   {}, this.defaultHandlerOptions
			               );
			               OpenLayers.Control.prototype.initialize.apply(
			                   this, arguments
			               ); 
			               this.handler = new OpenLayers.Handler.Click(
			                   this, {
			                       'click': this.trigger
			                   }, this.handlerOptions
			               );
			           }, 
			    
			           trigger: function(e) {
			           		if(handle_add_place_click != false && add_place_open == true) {
			    				var new_place_lonlat = map.getLonLatFromViewPortPx(e.xy);
			    				new_place.move(new_place_lonlat);
			    				update_add_place(new_place_lonlat.lon, new_place_lonlat.lat);
			        			maps_debug("Add marker moved (click): "+new_place_lonlat.lat+", "+new_place_lonlat.lon);
			        		}
			           }
			     });
			    
			    // Add click-handler to the map
			    var new_place_click = new OpenLayers.Control.Click();
			    map.addControl(new_place_click);
			    new_place_click.activate();
			
			    add_place_initialized_once = true;
			    
			}
			else { maps_debug("Showing old layers for adding a new place."); }
			
	
	
		}// json got data?
	});//json call end

	// Hides possibly open pages and cards
	close_page();
	close_cards();

}

function close_add_place() {
	if(add_place_open == true) {
		add_place_open = false;
		/*
   		add_place_target.destroyFeatures([new_place]);
		new_place.destroy();
		new_place = null;
		*/
			
		/*
		add_place_drag.deactivate();
		new_place_click.deactivate();
		*/
		//add_place_target.destroyFeatures(0);
		
		//new_place.destroy();

		//add_place_target.destroy();
		
		hidePlacePanel();
		maps_debug("Closing add Place panel.");
		add_place_target.setVisibility(false);
	}
}


function update_add_place(q_lon, q_lat, needsConverting) {
	maps_debug("Updating add place -info.");

	var add_new_place_form = $("#add_new_place_form");

	add_new_place_form.find("#address_row").hide();
	add_new_place_form.find("#address_row .flag").hide();
	add_new_place_form.find("#address_row .address_row").text("");
	add_new_place_form.find("#loading_row").show();

	// Convert coordinates to the "Google projection"
	var g_lonLat = new OpenLayers.LonLat(q_lon, q_lat).transform(projmerc, proj4326);

	maps_debug("update_add_place() got coords: "+q_lat+", "+q_lon+" => conv: "+g_lonLat.lat+", "+g_lonLat.lon);

	add_new_place_form.find("input#lat").val(g_lonLat.lat);
	add_new_place_form.find("input#lon").val(g_lonLat.lon);

	// Reverse Geocode latlon -> address
	//$.getJSON('ajax/geocoder.php?mode=reverse&q=' + g_lonLat.lat + ',' + g_lonLat.lon, function(data) {				
	$.ajax({
		// Define AJAX properties.
		method: "get",
		url: 'ajax/geocoder.php?mode=reverse&q=' + g_lonLat.lat + ',' + g_lonLat.lon, // + '&c=' + Math.random()
		dataType: "json",
		timeout: 10000, // timeout in milliseconds; 1s = 1000ms
	 
		// Got a place
		success: function(data){
			add_new_place_form.find("#loading_row").hide();

			if(data.error==true) {
				maps_debug("Reverse geocode returned an error.");
				add_place_manual_locality_selector();
			} 
			
			// If no country regogniced, we cannot use this info - then go manual
			else if(data.country_name == undefined || data.country_code == '' || data.country_code == undefined || data.country_name == 'false') {
					maps_debug("Received a rewerse geocode data, but for this location no country info. (huh?)");
					add_place_manual_locality_selector();
			}
			
			// All seems to be ok, let's see what we got...
			else {
				maps_debug("Reverse geocoder answered:<br />-country_name: '"+data.country_name+"'<br />-county_code: '"+data.country_code+"'<br />-locality: '"+data.locality+"'<br />-address: '"+data.address+"'");
			
				// Country info
				add_new_place_form.find("#address_row #country_name").text(data.country_name);
				add_new_place_form.find("#address_row .flag").hide().attr("src","static/gfx/flags/"+data.country_code.toLowerCase()+".png").fadeIn('slow');
				add_new_place_form.find("input#country_iso").val(data.country_code);


				// Full address
				if(data.address != "" || data.address != ",") {
					add_new_place_form.find("#address_row #address").html(data.address);
				} else {
					add_new_place_form.find("#address_row #address").text("");
				}
				
				if(data.address != "" && data.country_name != "") {
					add_new_place_form.find("#address_row #address").append("<br />");
				}
				
				
				// City
				if(data.locality != undefined) {
					add_new_place_form.find("input#locality").val(data.locality);
					add_new_place_form.find("#locality_name").text(data.locality);
					
					if(data.country_name != undefined && data.country_code != undefined) {
						add_new_place_form.find("#locality_name").append("<br />");
					}
					
					add_new_place_form.find("#locality_name").show();
					
				}
				else {
					add_new_place_form.find("input#locality").val("");
					add_new_place_form.find("#locality_name").hide().text("");
				}
				
				// Show all that content now
				add_new_place_form.find("#address_row").show();
				
			} // else after no errors...
			
		}, 
		// Didn't find anything...
		error: function( objAJAXRequest, strError ){
			$("#add_new_place_form #loading_row").hide();
			maps_debug("Error when trying to get reverce geocode. "+strError);
			add_place_manual_locality_selector();
		}
	}); // end ajax
	
}
function add_place_manual_locality_selector() {
	maps_debug("Show manual locality selector for add a place -panel.");
	var add_new_place_form = $("#add_new_place_form");
   	add_new_place_form.find("input#country_iso").val("");
   	add_new_place_form.find("input#locality").val("");
   	add_new_place_form.find("#address_row").hide();
   	add_new_place_form.find("#manual_country_selection").show();
}


/* 
 * Show marker panel
 */
function showPlacePanel(id, zoomin) {
	maps_debug("Show marker panel for place: "+id);
	stats("show_place/?place="+id);

	close_add_place();

	$.ajax({
		url: "ajax/place.php?id="+id+"&lang="+locale,
		async: false,
		success: function(content){
		
			maps_debug("Loaded marker data OK. Show panel.");
			$("#PlacePanel").html(content).show();
			
			// Shrink map a bit and make some space for the panel
			$("#map").css("right","250px");
			
			// Zoom in into a marker if requested so
			if(zoomin == true) {
			    zoomMapIn($("#PlacePanel #coordinates .lat").text(), $("#PlacePanel #coordinates .lon").text(), 16);
			}
			
      	}
	});
	
	
}


/* 
 * Hide marker panel
 */
function hidePlacePanel() {
	maps_debug("Hiding Place Panel.");
	
	// Map to full width again
	$("#map").css("right","0");
	$("#PlacePanel").hide().html("");
}


function place_history(place_id, place_language) {
	maps_debug("Open edit history for a place "+place_id);
	
	if(place_language != undefined || place_language != "" || place_language != false) { place_language2 = "&place_lang="+place_language; }
	else place_language2 = "";

	open_page("log_place", "place_id="+place_id+place_language2);
}


/* 
 * Search
 */
function search(q) {
	maps_debug("Search: "+q);
	stats("search/?s="+q);
	
	show_loading_bar(_("Searching..."));

	// Geocode
	//$.getJSON('ajax/geocoder.php?q=' + q, function(data) {
	$.ajax({
		// Define AJAX properties.
		method: "get",
		url: 'ajax/geocoder.php?q=' + q,
		dataType: "json",
		timeout: 10000, // timeout in milliseconds; 1s = 1000ms
	 
		// Got a place
		success: function(data){
		
			// Hide "searching"
			hide_loading_bar();
			
			maps_debug("Search results came from: "+data.service+"<br /> - Locality: "+data.locality+"<br /> - Country: "+data.country_code);
			
			// If we got a bounding box as an answr, use it:
			if(data.boundingbox != undefined) {
		
				//maps_debug("Search found: lat: "+data.lat+", lon: "+data.lon);
				maps_debug("Moving to the bounding box: "+data.boundingbox);
				
				// build a bounding box coordinates and zoom in
				var boundingbox = data.boundingbox.split(',');
				
				bounds = new OpenLayers.Bounds();
				bounds.extend( new OpenLayers.LonLat(boundingbox[2],boundingbox[0]) );
				bounds.extend( new OpenLayers.LonLat(boundingbox[3],boundingbox[1]) );
				
				map.zoomToExtent( bounds );
			}
			else if(data.lat != undefined && data.lon != undefined) {
				maps_debug("Moving to lat+lon.");
				
				if(data.zoom == undefined) searchZoom = 5;
				else searchZoom = data.zoom;
				
				zoomMapIn(data.lat, data.lon, searchZoom);
			}
			// We got a result, but nada...
			else {
				maps_debug("Search didn't find anything.");
				info_dialog('<p>'+_("Your search did not match any places.")+'</p><p>'+_("Try searching in English and add a country name in to your search.")+'</p><p>'+_("Example:")+' Vilnius, Lithuania.</p>', _('Not found'), false);
			}
		},
	 
	 
		// Didn't find anything...
		error: function( objAJAXRequest, strError ){
			maps_debug("Search didn't find anything. Error type: "+strError);
			
			// Hide "searching"
			hide_loading_bar();
			
			info_dialog('<p>'+_("Your search did not match any places.")+'</p><p>'+_("Try searching by english city names or/and add a country name with cities."), _('Not found'), false);
		}
	});
	
	
			
	//});
	
	// Close open stuff
	close_cards();
	close_page();
	
    return false;
    
}


/* 
 * Zoom map in to a point
 */
function zoomMapIn(lat, lon, zoom) {
	maps_debug("Zoom map to a point. "+lat+","+lon);
	map.setCenter(new OpenLayers.LonLat(lon, lat).transform(proj4326, projmerc));
	map.zoomTo(zoom);
}


/*
 * Show information about country
 * TODO
 */
function showCountry(country_iso) {
	maps_debug("Information about country "+country_iso);

	open_page("countries");
/*	
	// Show selected country after page has opened
*/
}


/* 
 * Open page
 */
function open_page(page_name, variables, open_at_start) {
    maps_debug("Open a page: "+page_name);
    stats("pages/"+page_name+"/");

    if(open_at_start == false || open_at_start == undefined) {

		if(variables == false || variables == undefined) { 
			variables = "";
		} else {
			variables = "&"+variables;
		}
		
		// Close cards if open
		close_cards();
	
		$.ajax({
			url: "ajax/views.php?type=page&lang="+locale+"&page=" + page_name + variables,
			async: false,
			success: function(content){

				var page = $("#pages .page");
	
				// If page area is hidden
				if(page.is(':hidden')) {
					page.attr("id", page_name);
					$("#pages .page .content").html(content).show();
					page.slideDown('fast');
					$("#pages .close").fadeIn();
				// Page area visible, just load new content in it
				} else {
					page.attr("id", page_name);
					$("#pages .page .content").html(content);
					page.attr({ scrollTop: 0 });
				}
				return true;
    	  	}
		});
    }
	// Page content was already loaded at the php parser, this function needs just to set correct css attribute
    else {
		$("#pages .page").attr("id", page_name);
		return true;
    }

}




/* 
 * Close page
 */
function close_page() {
	maps_debug("Closing a page");

	if($("#pages .page").is(':visible')) {
			$("#pages .page .content").hide('fast').text('');
			$("#pages .close").fadeOut('fast');
			$("#pages .page").slideUp('fast').attr(id,"closed");
	}
	return true;
}


/* 
 * Open card
 */
function open_card(name, title) {
	maps_debug("Open a card: "+name);
	stats("cards/"+name+"/");
		
	close_cards();
    
	$.ajax({
	    url: "ajax/views.php?type=card&lang="+locale+"&page=" + name,
	    async: false,
	    success: function(content){

	    	$("#cards").html('<div class="card" id="card_'+name+'" title="'+title+'">'+content+'</div>');
	    	$("#cards .card").dialog({
						position: [100,100],
						height: 400,
						width: 390,
	    				maxHeight: 600,
	    				maxWidth: 650,
	    				show: 'slide'
			});
			$("#cards .card a").blur();
      	}
	});
	
	// Close pages if open
	if($("#pages .page").is(':visible')) { close_page(); }

}


/* 
 * Close all open cards
 */
function close_cards() {
	//if($("#cards .card").is(':visible')) {
		//maps_debug("Closing all cards...");
		$(".card:visible").dialog("close");
	//}
}


				    
/*
 * Save written description
 */
function saveDescription(post_place_id, post_language, post_description) {
    
    maps_debug("Saving description for place #"+post_place_id);
	show_loading_bar(_("Saving..."));

    $.post('api/?add_description', { place_id: post_place_id, language: post_language, description: post_description }, 
        function(data) {
        
	        hide_loading_bar();
        
        	if(data.success == true) {
        		maps_debug("Description saved. lang: "+post_language+", post-id: "+post_place_id);
        		showPlacePanel(post_place_id);
        		return data.description;
        	}
        	// Oops!
        	else {
        	    info_dialog(_('Updating description failed.')+'<br /><br />'+_('Please try again!'), _("Error"), true);
        	    maps_debug("Updating description failed. <br />- Error: "+data.error+"<br />- Data: "+data);
        	    return false;
        	}
        
        }, "json"
    ); // post end
    
}


/*
 * Function to remove comment
 * Produces an error popup if current logged in user doesn't have any permission
 */
function removeComment(remove_id) {
    maps_debug("Asked to remove a comment "+remove_id);
	stats("comment/remove/");

	var confirm_remove = confirm(_("Are you sure you want to remove this comment?"));

	if(confirm_remove) {
		// Call API
		$.getJSON('api/?remove_comment='+remove_id, function(data) {
		
			if(data.success == true) {
		
    			maps_debug("Comment "+remove_id+" removed.");
			
				// Fade comment away
    			$("#comment_list #comment-"+remove_id).fadeOut("slow");
    	
    			// Minus one from comment counter
    			var current_comment_count = $("#comments #comment_counter").text();
    			$("#comments #comment_counter").text(parseInt(current_comment_count)-1);
    			
			} else {
				info_dialog(_("Could not remove comment due error. Please try again!"), _("Error"), true);
    			maps_debug("Could note remove comment. Error: "+data.error);
			}
		
		});
	}
}


/* 
 * Validate numeric
 * http://stackoverflow.com/questions/18082/validate-numbers-in-javascript-isnumeric
 */
function is_numeric(input)
{
   return (input - 0) == input && input.length > 0;
}


/* 
 * Show simple info/error dialog for user
 */
function info_dialog(dialog_info, dialog_title, dialog_alert, reload_page) {
	
	if(dialog_alert) { var dialog_type = "alert"; }
	else { var dialog_type = "info"; }
	
	if(dialog_title == undefined) { dialog_title = dialog_type; }
	
	maps_debug("Calling "+dialog_type+"-dialog box; "+dialog_title);
	
	
	
	$("#dialog-message")
		.attr("title",dialog_title)
		.html('<p><span class="ui-icon ui-icon-'+dialog_type+'" style="float:left; margin:0 7px 50px 0;"></span>'+dialog_info+'</p>')
		.dialog({
		modal: true,
		resizable: false,
		buttons: {
			Ok: function() {
				if(reload_page) { 
					maps_debug("Reloading the page...");
					$("#reloadPage").submit();
					$(this).dialog('close');
				} else {
					$(this).dialog('close');
					maps_debug("Dialog closed.");
				}
			}
		}
	});
	
	dialog_info = null;
	dialog_title = null;
	dialog_alert = false;
}


/*
 * Make a graphical on/off slider out of checkbox-input
 *
 * Usage:
 *
	$("input#target").onoff_toggle({
	    onClickOff: function(){
	    	// a callback when turning off
	    },
	    onClickOn: function(){
	    	// a callback when turning on
	    }
	});
 */
(function($){
	$.fn.onoff_toggle = function(options) {
	
		var defaults = {
			onClickOn: function(){},
			onClickOff: function(){}
		},
		settings = $.extend({}, defaults, options);
	
		var checkbox = $(this);
		var name = $(this).attr("id");

		// Do we start from on or off state?
		if(checkbox.is(":checked")) var state = "on";
		else var state = "off";
		
		// Fire when checkbox gets clicked
		checkbox.change(function(){
		    onoff_change(checkbox);
		});

		// Add a clickable element
		checkbox.after('<a href="#" id="onoff_'+name+'" class="onoff_toggle '+state+'"><span></span></a>');
		checkbox.next("a.onoff_toggle").click(function(e){
		    e.preventDefault();
		    
		    if(checkbox.is(":checked")) checkbox.attr("checked", false);
		    else checkbox.attr("checked", true);
		    
		    onoff_change(checkbox);
		});

		function onoff_change(toggle_target) {
		
		    if(toggle_target.is(":checked")) {
		    	var toggled_position = '0 bottom';
				settings.onClickOn.call(this); //Callback after the slide turns the toggle off
		    }
		    else {
		    	var toggled_position = '-54px bottom';
				settings.onClickOff.call(this); //Callback after the slide turns the toggle on
		    }
		    
		    toggle_target.next("a.onoff_toggle").animate({
		      'background-position': toggled_position
		    }, 250);
		}
		
		// Hide checkbox
		$(this).hide();

	};
})(jQuery);


/* 
 * Show simple loading animation
 */
function show_loading_bar(title) {
	maps_debug("Show loading bar: "+title);
	
	if(title != undefined) { $("#loading-bar .title").text(title); }
	else { $("#loading-bar .title").text(""); }
	
	if($("#loading-bar").is(":hidden") == true) {
		$("#loading-bar").show();
	}
}


/* 
 * Show simple loading animation
 */
function hide_loading_bar() {
	maps_debug("Hide loading bar.");
	
	if($("#loading-bar").is(":visible") == true) {
		$("#loading-bar").fadeOut('slow');
	}
	$("#loading-bar .title").text("");
}


/* 
 * Log debug events
 */
function maps_debug(str) {
	log_list.append("<li><span>"+str+"</span></li>");
	if(log.is(":visible")) log_list.attr({ scrollTop: $("#log ol").attr("scrollHeight") });
}

/*
 * Log events to the database
 * event: max 80 char string id
 * data: json array
 */
function maps_log(event, data) {
	return true; // Not functional yet
}


/*
 * Analytics
 * Gather statistics
 */
function stats(str) {
	if(str != undefined && str != "") {
		if(google_analytics == true) {
			maps_debug("Analytics (Google): "+str);
			_gaq.push(['_trackPageview', str]);
		}
		if(piwik_analytics == true) {
			maps_debug("Analytics (Piwik): "+str);
			/*
				Track piwik here...
			*/
		}
	
	} else { maps_debug("Error: empty stats() request!"); }
}
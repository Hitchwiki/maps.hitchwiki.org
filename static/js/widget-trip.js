
var proj4326 = new OpenLayers.Projection("EPSG:4326");
var projmerc = new OpenLayers.Projection("EPSG:900913");

// Missing tiles from the map
OpenLayers.Util.onImageLoadError = function(){this.src=basehref+'static/gfx/openlayers/tile_not_found.gif';}
OpenLayers.Tile.Image.useBlankTile=false;

var markersZoomLimit = 3;

var markers_free = false;
var map, trip_markers, map_center;

$(document).ready(function() {

	// Remove JS-required alert	
	$("#map").text('');

	// Custom images from our own server
	OpenLayers.ImgPath = basehref+"static/gfx/openlayers/";
	
	// Create map with controls	
	map = new OpenLayers.Map('map', {		
		projection: proj4326,
		displayProjection: projmerc,
		units: "m",
		numZoomLevels: 6,
		maxResolution: 156543.0339,
		maxExtent: new OpenLayers.Bounds(-20037508, -20037508, 20037508, 20037508.34),
/*		eventListeners: {
		    "moveend": refreshMapMarkers
		},
*/
		eventListeners: {
			"move": nullEvent,
		    "moveend": refreshMapMarkers,
		    "zoomend": nullEvent,
		    "changelayer": nullEvent,
		    "changebaselayer": nullEvent
		},
		
		controls: [
			new OpenLayers.Control.Navigation(),
			new OpenLayers.Control.PanZoomBar(),
			//new OpenLayers.Control.ScaleLine(),
			new OpenLayers.Control.LayerSwitcher({'ascending':false})
			//new OpenLayers.Control.Permalink('permalink'),
			//new OpenLayers.Control.Permalink(),
			//new OpenLayers.Control.KeyboardDefaults(),
			//new OpenLayers.Control.MousePosition(),
			//new OpenLayers.Control.OverviewMap()
	    ]
	});
 
	// Get rating from marker

	function nullEvent() { return true; }
	
	var tripContext = {
		/*
	    getColor: function(feature) {
	        return colors[feature.attributes["rating"]];
	    }*/
	};
	

	// Initialize a layer for trip markers
	// You can fill it with refreshMapMarkers() using listener events
	trip_markers = new OpenLayers.Layer.Vector(
		"Trips", {
			styleMap: new OpenLayers.StyleMap({
	                	"default": new OpenLayers.Style({
					graphicZIndex: 1,
					pointRadius: 3,//"${radius}",
					strokeWidth: 1,
					cursor: "pointer",
					fillColor: "#e94d00",
					strokeColor: "#e94d00"
				}, {context: tripContext}),
	                	"select": new OpenLayers.Style({
					graphicZIndex: 2,
					fillColor: "#fde669"
	                	}),
	                	"hover": new OpenLayers.Style({
					graphicZIndex: 2,
					fillColor: "#fde669"
				})
			}), //stylemap end
			isBaseLayer: false,
			rendererOptions: {yOrdering: true}
        }
	);//trip markers end

	// Current location layer
	if(show_current_location==true) {
		var current_location_marker = new OpenLayers.Layer.Markers( "Current location" );
		map.addLayer(current_location_marker);
		
	        var current_location_size = new OpenLayers.Size(24,35);
	        var current_location_offset = new OpenLayers.Pixel(-(current_location_size.w/2), -current_location_size.h);
	        var current_location_icon = new OpenLayers.Icon('/devmaps/static/gfx/current_location.png', current_location_size, current_location_offset);
	        current_location_marker.addMarker(new OpenLayers.Marker(new OpenLayers.LonLat(current_location_lon, current_location_lat).transform(proj4326, projmerc), current_location_icon));
	} // show_current_location end


	// The map layer
	if(map_layer == "gphy") {
		var base_layer = new OpenLayers.Layer.Google(
		    "Google Physical",
		    {
		    	visibility: true,
		    	sphericalMercator: true, 
		    	type: G_PHYSICAL_MAP
		    }
		);
	}
	else if(map_layer == "gmap") {
		var base_layer = new OpenLayers.Layer.Google(
		    "Google Streets",
		    {
		    	visibility: true, 
		    	sphericalMercator: true, 
		    	numZoomLevels: 20
		    }
		);
	}
	else if(map_layer == "ghyb") {
		var base_layer = new OpenLayers.Layer.Google(
		    "Google Hybrid",
		    {
		    	visibility: true,
		    	sphericalMercator: true, 
		    	type: G_HYBRID_MAP, 
		    	numZoomLevels: 20
		    }
		);
	}
	else if(map_layer == "gsat") {
		var base_layer = new OpenLayers.Layer.Google(
		    "Google Satellite",
		    {
		    	visibility: true,
		    	sphericalMercator: true, 
		    	type: G_SATELLITE_MAP, 
		    	numZoomLevels: 22
		    }
		);
	}
	// Default is OSM
	else {
		var base_layer = new OpenLayers.Layer.OSM("Open Street Map");
	}
	
	
	// Add produced layers to the map
	map.addLayers([base_layer,trip_markers]);
	//map.setBaseLayer(base_layer);


	// Initialize a layer for trip lines
	var from = new OpenLayers.LonLat(-0.14849, 51.52039).transform(proj4326, projmerc);
	var to = new OpenLayers.LonLat(60.131, 21.51083).transform(proj4326, projmerc);

        //var trip_lines = new OpenLayers.Layer.Vector("Lines"); 

	trip_lines = new OpenLayers.Layer.Vector(
		"Lines", {
			styleMap: new OpenLayers.StyleMap({
	                	"default": new OpenLayers.Style({
					strokeColor: '#FF0000',
			                strokeWidth: 2
				})
			}), //stylemap end
			isBaseLayer: false,
			rendererOptions: {yOrdering: true}
        }
	);//trip lines end



        map.addLayer(trip_lines);
        map.addControl(new OpenLayers.Control.DrawFeature(trip_lines, OpenLayers.Handler.Path));


	// Add current location layer and selecting -ability of the marker
	if(show_current_location==true) {
		map.addLayer(current_location_marker);
	}


	// Selecting trips
	var select_trip = new OpenLayers.Control.SelectFeature(trip_markers, 
							{
								onSelect: onTripSelect, 
							/*	onUnselect: onFeatureUnselect,*/
								hover: false,
								clickout: true,
								multiple: false,
								box: false
							});
	map.addControl(select_trip);
	select_trip.activate();
    
    
	// Set map
	map.setCenter(new OpenLayers.LonLat(lon, lat).transform(proj4326, projmerc));
	map.zoomTo(zoom);

	// Let markers be freeeee
	markers_free = true;
	refreshMapMarkers();
});

 function onTripSelect(feature) {
	maps_debug("Open trip #"+feature.attributes.id);

	alert("Would open a trip #"+feature.attributes.id);

	//window.top.location = '../?place='+feature.attributes.id;
}

var markers = new Array();
var lines = new Array();
function refreshMapMarkers() {

	var currentZoom = map.getZoom();
	
	// Hide markers layer if zoom level isn't deep enough
	if(currentZoom < markersZoomLimit) {
		//trip_lines.setVisibility(false);
		trip_markers.setVisibility(false);
	}
	else {
		//trip_lines.setVisibility(true);
		trip_markers.setVisibility(true);
	}
	
	if(currentZoom >= markersZoomLimit && markers_free==true) {

	map_center = map.getCenter();
	
	maps_debug("refreshMapMarkers called.");

		// Get corner coordinates from the map
		var extent = map.getExtent();
		var corner1 = new OpenLayers.LonLat(extent.left, extent.top).transform(projmerc, proj4326);
		var corner2 = new OpenLayers.LonLat(extent.right, extent.bottom).transform(projmerc, proj4326);
		
		
		var apiCall = '../api/?trips&user_id='+user_id+'&bounds='+corner2.lat+','+corner1.lat+','+corner1.lon+','+corner2.lon;	
		maps_debug("Calling API: "+apiCall);
		
		// Get markers from the API for this area
		$.getJSON(apiCall, function(data) {

		    // Go trough all trip-markers
		    if(data.error) {
		    	maps_debug("API Error: "+data.error);
		    }
		    else {
		    	maps_debug("Starting trip-markers each-loop...");
		    	
		    	// Loop markers we got trough 
		    	var markerStock = [];
		    	$.each(data, function(key, value) {
		    	
		    		// Check if marker isn't already on the map
		    		// and add it to the map
		    		if(markers[value.id] != true) {
		    			markers[value.id] = true;
		    			
		    			//maps_debug("Adding marker #"+value.id +"<br />("+value.lon+", "+value.lat+")...");
		    			
		    	        var coords = new OpenLayers.LonLat(value.lon, value.lat).transform(proj4326, projmerc);
		    	        
		    	        markerStock.push(
		    	            new OpenLayers.Feature.Vector(
		    	                new OpenLayers.Geometry.Point(coords.lon, coords.lat),
		    					{
		    						id: value.id,
		    						trip_id: value.trip_id
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
				trip_markers.addFeatures(markerStock);
		    	} else {
		    		maps_debug("Loop ended. No new markers found from this area.");
		    	}

		    	// Loading done, hide loading bar
		    	hide_loading_bar();
		    } // else error?
		    
		// getjson * end
		});



		/*
		 * Add lines to the map
		 */
		var apiCall = '../api/?trips&lines&user_id='+user_id+'&bounds='+corner2.lat+','+corner1.lat+','+corner1.lon+','+corner2.lon;	
		maps_debug("Calling API: "+apiCall);
		
		// Get markers from the API for this area
		$.getJSON(apiCall, function(data) {

		    // Go trough all trip-lines
		    if(data.error) {
		    	maps_debug("API Error: (lines) "+data.error);
		    }
		    else {
		    	maps_debug("Starting trip-lines each-loop...");

		    	// Loop markers we got trough 
		    	var lineStock = [];
		    	$.each(data, function(trip_id, trip) {
		    	
				maps_debug("Found a trip "+trip_id);
			
				$.each(trip, function(line_key, line) {
		    		// Check if line isn't already on the map
		    		// and add it to the map
		    		if(lines[line.from.id+"-"+line.to.id] != true) {
		    			lines[line.from.id+"-"+line.to.id] = true;

					var line_from = new OpenLayers.LonLat(line.from.lon, line.from.lat).transform(proj4326, projmerc);
					var line_to = new OpenLayers.LonLat(line.to.lon, line.to.lat).transform(proj4326, projmerc);

					lineStock.push(
						new OpenLayers.Feature.Vector(
						    	new OpenLayers.Geometry.LineString(
								new Array(
									new OpenLayers.Geometry.Point(line_from.lon, line_from.lat),
									new OpenLayers.Geometry.Point(line_to.lon, line_to.lat)
								)
							),
							null,
							{
								strokeColor: '#8B0000',
								strokeWidth: 1
							}		
						)				
					);

			    	        //maps_debug("...done.");
				
		    		} 
		    		else {
		    			//maps_debug("marker #"+value.id +" already on the map.");
		    		}
				
				
				}); // trip->points each * end
				
		    	// trips each * end
		    	});
		    	
		    	if(lineStock.length > 0) {
		    		maps_debug("Loop ended. Adding "+lineStock.length+" new lines to the map.");
				trip_lines.addFeatures(lineStock);
		    	} else {
		    		maps_debug("Loop ended. No new lines found from this area.");
		    	}

		    	// Loading done, hide loading bar
		    	hide_loading_bar();
		    } // else error?
		    
		// getjson * end
		});

	}
	else if(currentZoom < markersZoomLimit && markers_free==true){
		hide_loading_bar();
	}

}

/*
 * Jumps map to the user's current location if it's public
 */
function go_to_current_location() {
	if(show_current_location==true) {
		map.setCenter(new OpenLayers.LonLat(current_location_lon, current_location_lat).transform(proj4326, projmerc));
		map.zoomTo(current_location_zoom);
		//refreshMapMarkers();
		return true;
	}
	else return false;
}


function maps_debug(str) {

		$("#log").append("<li>"+str+"</li>");
		$("#log").attr({ scrollTop: $("#log").attr("scrollHeight") });

}



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
	
	$("#loading-bar .title").text("");
	if($("#loading-bar").is(":visible") == true) {
		$("#loading-bar").hide();
	}
}


/*
 * JS Gettext
 */
function _(str) {
	return str;
}
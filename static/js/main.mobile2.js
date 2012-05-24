/*
 * Hitchwiki Mobile Maps: main.mobile.js
 */
// @requires jquery.min.js
// @requires jquery.mobile.min.js
// @requires OpenLayers.js
// @requires jquery.cookie.js

maps_debug("Current page set: " + current_page);

basehref = '../../';

// initialize map when page ready
if(current_page == "home") {
	var map;
	var proj4326 = new OpenLayers.Projection("EPSG:4326");
	var projmerc = new OpenLayers.Projection("EPSG:900913");
	
	// Custom images from our own server
	OpenLayers.Util.onImageLoadError = function(){this.src=basehref+'static/gfx/openlayers/tile_not_found.gif';}
	OpenLayers.Tile.Image.useBlankTile=false;
	OpenLayers.ImgPath = basehref+"static/gfx/openlayers/";
	
	// Release marker API later...
	var markers_free = false;
}

var init_map = function () {

	maps_debug("=== INIT MAP ===");
            
    var location_layer = new OpenLayers.Layer.Vector("Vector Layer", {
    	displayInLayerSwitcher: false
    });
    
			
			
/*
    var sprintersLayer = new OpenLayers.Layer.Vector("Sprinters", {
        styleMap: new OpenLayers.StyleMap({
            externalGraphic: basehref+"/static/mobile/gfx/mobile-loc.png",
            graphicOpacity: 1.0,
            graphicWidth: 16,
            graphicHeight: 26,
            graphicYOffset: -26
        })
    });

    var sprinters = getFeatures();
    sprintersLayer.addFeatures(sprinters);

    var selectControl = new OpenLayers.Control.SelectFeature(sprintersLayer, {
        autoActivate:true,
        onSelect: onSelectFeatureFunction});
*/
    var geolocate = new OpenLayers.Control.Geolocate({
        id: 'locate-control',
        geolocationOptions: {
            enableHighAccuracy: false,
            maximumAge: 0,
            timeout: 7000
        }
    });
    
    

	/*
	 * Map layers
	 * Control loading of these from config.php
	 * OSM will be always loaded and used as a default
	 */
	 
	
	// OSM layer
	var mapnik = new OpenLayers.Layer.OSM();
	
	// OSM layer 2
	var osmarender = new OpenLayers.Layer.OSM(
	    "Open Street Map - Tiles @ Home",
	    "http://tah.openstreetmap.org/Tiles/tile/${z}/${x}/${y}.png"
	);
	

	// Google API V2 layers
	if(layer_google == true && google_maps_api_v2 == true) {

		var gmap = new OpenLayers.Layer.Google(
		    ("Google "+_("Streets")),
		    {
		    	visibility: false, 
		    	sphericalMercator: true, 
		    	numZoomLevels: 20
		    }
		);
		var gsat = new OpenLayers.Layer.Google(
		    ("Google "+_("Satellite")),
		    {
		    	visibility: false, 
		    	sphericalMercator: true, 
		    	type: G_SATELLITE_MAP, 
		    	numZoomLevels: 22
		    }
		);
		var ghyb = new OpenLayers.Layer.Google(
		    ("Google "+_("Hybrid")),
		    {
		    	visibility: false, 
		    	sphericalMercator: true,
		    	type: G_HYBRID_MAP, 
		    	numZoomLevels: 20
		    }
		);
		var gphy = new OpenLayers.Layer.Google(
		    ("Google "+_("Physical")),
		    {
		    	visibility: false, 
		    	sphericalMercator: true, 
		    	type: G_PHYSICAL_MAP
		    }
		);
	}//google end

	// Google API V3 layers
	else if(layer_google == true) {
	
		var gmap = new OpenLayers.Layer.Google(
		    ("Google "+_("Streets")),
		    {
		    	visibility: false, 
		    	sphericalMercator: true, 
		    	animationEnabled: true,
		    	numZoomLevels: 20
		    }
		);
		var gsat = new OpenLayers.Layer.Google(
		    ("Google "+_("Satellite")),
		    {
		    	visibility: false, 
		    	sphericalMercator: true, 
		    	animationEnabled: true,
		    	type: google.maps.MapTypeId.SATELLITE, 
		    	numZoomLevels: 22
		    }
		);
		var ghyb = new OpenLayers.Layer.Google(
		    ("Google "+_("Hybrid")),
		    {
		    	visibility: false, 
		    	sphericalMercator: true, 
		    	animationEnabled: true,
		    	type: google.maps.MapTypeId.HYBRID, 
		    	numZoomLevels: 20
		    }
		);
		var gphy = new OpenLayers.Layer.Google(
		    ("Google "+_("Physical")),
		    {
		    	visibility: false, 
		    	sphericalMercator: true, 
		    	animationEnabled: true,
		    	type: google.maps.MapTypeId.TERRAIN
		    }
		);
	}//google end
	

	// create Bing layers
	if(layer_bing == true) {
	
		var bmap = new OpenLayers.Layer.Bing(
		    {
				name: "Bing "+_("Streets"),
				key: layer_bing_key,
				type: "Road"
		    }
		);
		var bsat = new OpenLayers.Layer.Bing(
		    {
				name: "Bing "+_("Satellite"),
				key: layer_bing_key,
				type: "Aerial"
		    }
		);
		var bhyb = new OpenLayers.Layer.Bing(
		    {
				name: "Bing "+_("Hybrid"),
				key: layer_bing_key,
				type: "AerialWithLabels"
		    }
		);
		
	}// bing end

	// create Nokia Ovi layers
	if(layer_ovi == true) {

        var omap = new OpenLayers.Layer.XYZ(
		    ("Nokia Ovi "+_("Street")),
        	["http://a.maptile.maps.svc.ovi.com/maptiler/maptile/newest/normal.day/${z}/${x}/${y}/256/png8","http://b.maptile.maps.svc.ovi.com/maptiler/maptile/newest/normal.day/${z}/${x}/${y}/256/png8"], 
        	{
				transitionEffect: 'resize', 
				sphericalMercator: true, 
				numZoomLevels: 21
        	}
        );
        var osat = new OpenLayers.Layer.XYZ(
		    ("Nokia Ovi "+_("Satellite")),
        	["http://e.maptile.maps.svc.ovi.com/maptiler/maptile/newest/hybrid.day/${z}/${x}/${y}/256/png8","http://f.maptile.maps.svc.ovi.com/maptiler/maptile/newest/hybrid.day/${z}/${x}/${y}/256/png8"],
            {
				transitionEffect: 'resize', 
				sphericalMercator: true, 
				numZoomLevels: 21
        	}
        );
        var otra = new OpenLayers.Layer.XYZ(
		    ("Nokia Ovi "+_("Transit")),
        	["http://c.maptile.maps.svc.ovi.com/maptiler/maptile/newest/normal.day.transit/${z}/${x}/${y}/256/png8","http://d.maptile.maps.svc.ovi.com/maptiler/maptile/newest/normal.day.transit/${z}/${x}/${y}/256/png8"], 
        	{
				transitionEffect: 'resize', 
				sphericalMercator: true, 
				numZoomLevels: 21
        	}
        );

	}//nokia ovi end

	
	
	
    // create map
    /*
    map = new OpenLayers.Map({
        div: "map",
        theme: null,
        projection: projmerc,
        numZoomLevels: 18,
        controls: [
            new OpenLayers.Control.Attribution(),
            new OpenLayers.Control.TouchNavigation({
                dragPanOptions: {
                    enableKinetic: true
                }
            }),
            geolocate,
            selectControl
        ],
        layers: [
            vector,
            sprintersLayer,
            
            mapnik, osmarender
             
        ],
        center: new OpenLayers.LonLat(lon, lat).transform(proj4326, projmerc),
        zoom: zoom
    });
    */
    
	// Create map with controls	
	map = new OpenLayers.Map({		
        div: "map",
        theme: null,
		projection: proj4326,
		displayProjection: projmerc,
		
		units: "m",
        numZoomLevels: 18,
		/*
		maxResolution: 156543.0339,
		maxExtent: new OpenLayers.Bounds(-20037508, -20037508, 20037508, 20037508.34),
		*/
		
		
        controls: [
            new OpenLayers.Control.Attribution(),
            new OpenLayers.Control.TouchNavigation({
                dragPanOptions: {
                    enableKinetic: true
                }
            }),
            geolocate,
            //selectControl
        ],
        layers: [
            location_layer,
            //sprintersLayer,
            
            mapnik, osmarender
             
        ],
        /*
		eventListeners: {
		    "moveend": refreshMapMarkers
		},
		*/
		
        center: new OpenLayers.LonLat(lon, lat).transform(proj4326, projmerc),
        zoom: zoom
        
	    
	});
    
    
	/*
	 * Add produced layers to the map
	 */
    if(layer_google == true) { map.addLayers([gmap, gsat, ghyb, gphy]); }
    if(layer_bing == true) { map.addLayers([bmap, bsat, bhyb]); }
    if(layer_ovi == true) { map.addLayers([omap, osat, otra]); }


 	// Different colors for markers depending on their rating
	var colors = [	
					"#ffffff", // rate 0
					"#00ad00", // rate 1
					"#96ad00", // rate 2
					"#ffff00", // rate 3
					"#ff8d00", // rate 4
					"#ff0000"  // rate 5
				];
	
	// Get rating from marker
	var markerContext = {
	    getColor: function(feature) {
	        return colors[feature.attributes["rating"]];
	    }
	};

	// Initialize a layer for the places
	// You can fill it with refreshMapMarkers() using listener events
	places = new OpenLayers.Layer.Vector(
		"Places", {
				styleMap: new OpenLayers.StyleMap({
                	"default": new OpenLayers.Style({
                	
    				    graphicZIndex: 1,
					    pointRadius: 7,//"${radius}",
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
                	    fillColor: "#66ccff"
                	    
                	})
                	
                	
                	
                }), //stylemap end
			isBaseLayer: false,
			rendererOptions: {yOrdering: true}
        }
	);//places end

	map.addLayers([places])

	// Selecting markers
	var select_marker = new OpenLayers.Control.SelectFeature(places, 
							{
								onSelect: onFeatureSelect, 
							/*	onUnselect: onFeatureUnselect,*/
								hover: false,
								clickout: true,
								multiple: false,
								box: false
							});
    map.addControl(select_marker);
    select_marker.activate();

	// When clicking place marker
	var descriptions = new Array();
	function onFeatureSelect(place) {
		maps_debug("Open #"+place.attributes.id);
        selectedPlace = place; 
        showPlacePanel(selectedPlace.attributes['id']);
	}


	
	// Let markers be freeeee
	markers_free = true;
	

	var markers = new Array();
	//function refreshMapMarkers() {
	map.events.register("moveend", map, function(e){
	
		var currentZoom = map.getZoom();
		
		// Hide markers layer if zoom level isn't deep enough, and show marker count-labels instead
		if(currentZoom < markersZoomLimit) {
			places.setVisibility(false);
		}
		else {
			places.setVisibility(true);
		}
		
		if(currentZoom >= markersZoomLimit && markers_free==true) {
		
		map_center = map.getCenter();
		
		maps_debug("refreshMapMarkers called.");
	
			// Get corner coordinates from the map
			var extent = map.getExtent();
			var corner1 = new OpenLayers.LonLat(extent.left, extent.top).transform(projmerc, proj4326);
			var corner2 = new OpenLayers.LonLat(extent.right, extent.bottom).transform(projmerc, proj4326);
			
			
			var apiCall = basehref+'api/?bounds='+corner2.lat+','+corner1.lat+','+corner1.lon+','+corner2.lon;	
			maps_debug("Calling API: "+apiCall);
			
			// Get markers from the API for this area
			$.getJSON(apiCall, function(data) {
			    // Go trough all markers
			    
			    
			    if(data.error) {
			    	maps_debug("API Error: "+data.error);
			    }
			    else {
			    	maps_debug("Starting markers each-loop...");
			    	
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
			    						rating: value.rating/*,
			    						description: value.description*/
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
			    	
			    	// Loading done, hide loading bar
			    	//hide_loading_bar();
			    } // else error?
			    
			// getjson * end
			});
	
		}
		else if(currentZoom < markersZoomLimit && markers_free==true){
			//maps_debug("hide loading bar");
			//hide_loading_bar();
		}
	
	}); // refreshMapMarkers
	
	



    var style = {
        fillOpacity: 0.1,
        fillColor: '#f7ad00',
        strokeColor: '#8c5600',
        strokeOpacity: 0.7,
		strokeWidth: 1
    };
    geolocate.events.register("locationupdated", this, function(e) {
        location_layer.removeAllFeatures();
        location_layer.addFeatures([
            new OpenLayers.Feature.Vector(
                e.point,
                {},
                {
                    graphicName: 'circle',
        			fillColor: '#8c5600',
                    strokeWidth: 0,
                    fillOpacity: 1,
                    pointRadius: 5
                }
            ),
            new OpenLayers.Feature.Vector(
                OpenLayers.Geometry.Polygon.createRegularPolygon(
                    new OpenLayers.Geometry.Point(e.point.x, e.point.y),
                    e.position.coords.accuracy / 2,
                    50,
                    0
                ),
                {},
                style
            )
        ]);
        map.zoomToExtent(location_layer.getDataExtent());
    });


};





// When map page opens get location and display map
//$('.page-map').live("pagecreate", function() {

	/*
	//boston :)
	var lat = 42.35843,
		lon = -71.059773;
	//try to get GPS coords
	if( navigator.geolocation ) {
			
		//redirect function for successful location	
		function gpsSuccess(pos){
			if( pos.coords ){ 
				lat = pos.coords.latitude;
				lon = pos.coords.longitude;
			}
			else{
				lat = pos.latitude;
				lon = pos.longitude;
			}
		}	
		
		function gpsFail(){
			//Geo-location is supported, but we failed to get your coordinates. Workaround here perhaps?
		}
		
		navigator.geolocation.getCurrentPosition(gpsSuccess, gpsFail, {enableHighAccuracy:true, maximumAge: 300000});
	}
*/
	/*
	if not supported, you might attempt to use google loader for lat,long
	$.getScript('http://www.google.com/jsapi?key=YOURAPIKEY',function(){
		lat = google.loader.ClientLocation.latitude;
		lon = google.loader.ClientLocation.longitude;
	});			
	*/
/*
	var latlon = new google.maps.LatLng(lat, lon);
	var myOptions = {
		zoom: 10,
		center: latlon,
		mapTypeId: google.maps.MapTypeId.ROADMAP
    };
    var map = new google.maps.Map(document.getElementById("map-canvas"),myOptions);
*/


//});







// Start with the map page
//window.location.replace(window.location.href.split("#")[0] + "#mappage");

var selectedPlace = null;

$(document).ready(function() {

    // fix height of content
    function fixContentHeight() {
    	
    	maps_debug("Action: pageload / orientationchange / resize / pageshow");
    	
        var footer = $("div[data-role='footer']:visible"),
            content = $("div[data-role='content']:visible:visible"),
            viewHeight = $(window).height(),
            contentHeight = viewHeight - footer.outerHeight();

        if ((content.outerHeight() + footer.outerHeight()) !== viewHeight) {
            contentHeight -= (content.outerHeight() - content.height() + 1);
            content.height(contentHeight);
        }

        if (current_page == "home" && window.map && window.map instanceof OpenLayers.Map) {
            map.updateSize();
            maps_debug("Update map size");
        } 
        else if(current_page == "home") {
            // initialize map
            
            init_map();
            /*
            init_map(function(feature) { 
                selectedPlace = feature; 
                $.mobile.changePage("#popup", "pop"); 
            });
            */
            initLayerList();
        }
    }
    $(window).bind("orientationchange resize pageshow", fixContentHeight);
    document.body.onload = fixContentHeight;

	if(current_page == "home") {

    	// Map zoom  
    	$("#plus").click(function(){
    	    map.zoomIn();
    	});
    	$("#minus").click(function(){
    	    map.zoomOut();
    	});
    	$("#locate").click(function(){
    		maps_debug("Locate me!");
    		
    	    var control = map.getControlsBy("id", "locate-control")[0];
    	    if (control.active) {
    	        control.getCurrentLocation();
    	    } else {
    	        control.activate();
    	    }
    	});

    }
    
	/*
	 * Place details
	 */
	 /*
	if(current_page == "home") {
    $('#place_info').live('pageshow',function(event, ui){
    
    	maps_debug("Loading place "+selectedPlace.attributes['id']);
            
		$.mobile.showPageLoadingMsg();
            
    	$("#place_info #place_info_content").hide();
    
		$.ajax({
			url: basehref+"ajax/mobile/place.php?id="+selectedPlace.attributes['id']+"&lang="+locale,
			async: false,
			success: function(content){
			
				maps_debug("Loaded marker data OK. Show place.");
				
				$("#place_info #place_info_content")
					.html(content)
					.show()
					.trigger( 'updatelayout' );
				

				$('#place_info #place_info_content ul#place_info_list').listview();
				$.mobile.hidePageLoadingMsg();
    	  	}
		});
	
        //$("ul#details-list").empty().append(li).listview("refresh");
    });
    }
    */


	/*
	 * Search functionality
	 */
	 
	// Search
	if(current_page == "search") {
    $('#searchpage').live('pageshow',function(event, ui){
        $('#query').bind('change', function(e){
            $('#search_results').empty();
            if ($('#query')[0].value === '') {
                return;
            }
            $.mobile.showPageLoadingMsg();

            // Prevent form send
            e.preventDefault();

            var searchUrl = 'http://ws.geonames.org/searchJSON?featureClass=P&maxRows=10';
            searchUrl += '&name_startsWith=' + $('#query')[0].value;
            $.getJSON(searchUrl, function(data) {
                $.each(data.geonames, function() {
                    var place = this;
                    $('<li>')
                        .hide()
                        .append($('<h2 />', {
                            text: place.name
                        }))
                        .append($('<p />', {
                            html: '<b>' + place.countryName + '</b> ' + place.fcodeName
                        }))
                        .appendTo('#search_results')
                        .click(function() {
                            $.mobile.changePage('#mappage');
                            var lonlat = new OpenLayers.LonLat(place.lng, place.lat);
                            map.setCenter(lonlat.transform(proj4326, projmerc), 10);
                        })
                        .show();
                });
                $('#search_results').listview('refresh');
                $.mobile.hidePageLoadingMsg();
            });
        });
        // only listen to the first event triggered
        $('#searchpage').die('pageshow', arguments.callee);
    });

	// Browse places
    $('#browse_places').live('pageshow',function(event, ui){
		
		init_search_browse("continent", false);
	        
        // only listen to the first event triggered
        $('#browse_places').die('pageshow', arguments.callee);
        
	});

	// Nearby places
    $('#search_nearby_places').live('pageshow',function(event, ui){

		alert("Couldn't find nearby places...");
	
	});
	} // is page search?
	
});


/*
 * Search functions
 */ 

if(current_page == "search") {
function init_search_browse(browse_view_type_this, browse_view_selected_item) {

		maps_debug("Init search by browsing: "+browse_view_type_this)

		// Determine list type etc
		if(browse_view_type_this == "continent") {
			var browse_view_api_call = "api/?continents";
			var browse_view_page_this = $("#browse_places");
			var browse_view_page_next = "#browse_places_country";
			var browse_view_type_next = "country";
			var browse_view_placelist = $("ul#placelist_continent");
		}
		else if(browse_view_type_this == "country") {
			var browse_view_api_call = "api/?countries&by_continent="+browse_view_selected_item;
			var browse_view_page_this = $("#browse_places_country ul.placelist");
			var browse_view_page_next = "#browse_places_city";
			var browse_view_type_next = "city";
			var browse_view_placelist = $("ul#placelist_country");
		}
		else if(browse_view_type_this == "city") {
			var browse_view_api_call = "api/?cities&by_country="+browse_view_selected_item;
			var browse_view_page_this = $("#browse_places_city");
			var browse_view_page_next = "./#mapview";
			var browse_view_type_next = false;
			var browse_view_placelist = $("ul#placelist_city");
		}

		//browse_view_page_this.page();

        browse_view_placelist.empty();
        $.mobile.showPageLoadingMsg();

		// Get list
		maps_debug("Calling API: "+browse_view_api_call);
		$.getJSON(basehref + browse_view_api_call, function(data) {


			var list_count = (data.length == undefined)? 100: data.length;
        	var letter_divider = null;

        	maps_debug("Got results ("+list_count+" lines) from API.");
        	
			if(data != null && !data.error && list_count > 0) {
			
	            $.each(data, function() {
	                var place = this;
	                
	                if(browse_view_type_this == "continent") {
	                	var li_name = place.name;
	                	var li_code = place.code;
	                	var li_places = place.places;
	                }
	                else if(browse_view_type_this == "country") {
	                	var li_name = place.name;
	                	var li_code = place.iso;
	                	var li_places = place.places;
	                }
	                else if(browse_view_type_this == "city") {
	                	var li_name = place.locality;
	                	var li_code = false;
	                	var li_places = place.places;
	                }
            
	                
	                // Don't show line if it doesn't have any places
	                // Mainly targeted to continents, as function returns them all
	                //maps_debug(li_name + " | " + li_code + " | " + li_places);
	                if(li_places > 0 && li_name != "" && li_name != null) {
	                
	                
					
					// Add A, B, C... dividers to the country/continent lists
					
					if(browse_view_type_this == "country" || browse_view_type_this == "city") {

						// Add divider at this point if list is bigger than 5 and if name has new first letter compared to previous ones 
						if(list_count > 15 && li_name.charAt(0) != letter_divider ) {
						
							letter_divider = li_name.charAt(0);
						
							$('<li>', {
							        "data-role": "list-divider",
							        text: li_name.charAt(0)
							    })
							    .appendTo(browse_view_placelist); // vaatiiko ID tekstitunnisteen vai jquery $hookin?
						
						} 
					}// ABC dividers
					
					
					
					
	                $('<li>')
	                    .hide()
	        			.append($('<a />', {
	        			    text: li_name,
	        			    "data-code": li_code
	        			})
	                    	// <img src="'.$settings["base_url"].'/static/gfx/flags/'.strtolower($li["iso"]).'.png" alt="" class="ui-li-icon">
							/*
	                    	.append($('<span />'), {
	                    		class: "ui-li-count",
	                    		text: li_places
	                    	})
	                    	*/
							.append('<span class="ui-li-count">'+li_places+'</span>')
	                    	.click(function(e) {
	
	                    	    maps_debug( "Selected: "+ li_name + " / "+li_code+" (@ "+browse_view_type_this+" list)");
	                    	    maps_debug( "Next page view: "+ browse_view_page_next );
	                    	    
	                    	    // Prepare next list
	                    	    if(browse_view_type_next != false) {
	                    	    	init_search_browse(browse_view_type_next, li_code);
	                    	    }
	                    	    
	                    	    $.mobile.changePage(browse_view_page_next);
	                    	})
	        
	        			)
	                    .appendTo(browse_view_placelist)
	                    .show();
	
		            } // no 0 places in list...
		            
            	}); // each
            	
            	$.when( browse_view_placelist.listview('refresh') ).then( $.mobile.hidePageLoadingMsg() );
            	
			
			} // if error
		    else {
		        alert(_("Error"));
		        $.mobile.hidePageLoadingMsg();
			}
           
			
        }); // json
    
} // init_search_browse end
} // is page search?





if(current_page == "home") {

/*
 * Map layers selector
 */
function initLayerList() {
	maps_debug("Init layer list");

    $('#layerspage').page();

	// Map layers
    var baseLayers = map.getLayersBy("isBaseLayer", true);
    $.each(baseLayers, function() {
        addLayerToList(this);
    });

    $('#layerslist').listview('refresh');
    
    map.events.register("addlayer", this, function(e) {
        addLayerToList(e.layer);
    });
} // initLayerList

function addLayerToList(layer) {
    var item = $('<li>', {
            "data-icon": "check",
            //"data-direction": "reverse",
            //"data-transition": "flip",
            "class": layer.visibility ? "checked" : ""
        })
        .append($('<a />', {
            text: layer.name
        })
            .click(function() {
                $.mobile.changePage('#mappage');
                if (layer.isBaseLayer) {
                    layer.map.setBaseLayer(layer);
                } else {
                    layer.setVisibility(!layer.getVisibility());
                }
            })
        )
        .appendTo('#layerslist');
    layer.events.on({
        'visibilitychanged': function() {
            $(item).toggleClass('checked');
        }
    });
} // addLayerToList

} // is page home?


/* 
 * Show marker panel
 */
function showPlacePanel(id) {
	maps_debug("Show marker panel for place: "+id);
	stats("show_place/?place="+id);

	$.mobile.changePage(basehref+"ajax/mobile/place.php?id="+id+"&lang="+locale, "pop");
}


/* 
 * Log debug events
 */
function maps_debug(str) {
	if(debug) {
		if(window.console || console.firebug) console.log(str);
	}
}


/*
 * Analytics
 * Gather statistics
 */
function stats(str) {
	if(str != undefined && str != "") {
		if(google_analytics == true) {
			maps_debug("Analytics (Google): mobile/"+str);
			_gaq.push(['_trackPageview', "mobile/"+str]);
		}
		if(piwik_analytics == true) {
			maps_debug("Analytics (Piwik): mobile/"+str);
			/*
				Track piwik here...
			*/
		}
	
	} else { maps_debug("Error: empty stats() request!"); }
}
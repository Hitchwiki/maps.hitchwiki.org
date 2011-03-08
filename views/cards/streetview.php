<?php
echo info_sign("This feature is under development and visible only for admins.",false);
?>
<div id="pano" style="width: 350px; height: 250px;"></div>

<script type="text/javascript">
    function google_streetview() {
      var panoOpts = {
        features: {
          streetView: true,
          userPhotos: true
        },
        userPhotoOptions: {
          photoRepositories: [ 'panoramio', 'picasa']
        }
      };
      var myPano = new GStreetviewPanorama(document.getElementById("pano"), panoOpts);
      var boston = new GLatLng(42.345573,-71.098326);
      GEvent.addListener(myPano, "error", handleNoFlash);  
      myPano.setLocationAndPOV(boston);
    }
    
    function handleNoFlash(errorCode) {
      if (errorCode == FLASH_UNAVAILABLE) {
        alert("Error: Flash doesn't appear to be supported by your browser");
        return;
      }
    }  
    
    google_streetview();
</script>
// Shiny-specific initialization
$(document).on("shiny:connected", function() {
    // Show landing page by default
    $("#landing").show();
    $("#about").hide();
    $("#browser").hide();
    
    // Handle navigation clicks
    $(document).on("click", "a[data-value='landing']", function(e) {
        $("#landing").show();
        $("#about").hide();
        $("#browser").hide();
    });
    
    $(document).on("click", "a[data-value='about']", function(e) {
        $("#landing").hide();
        $("#about").show();
        $("#browser").hide();
    });
    
    $(document).on("click", "a[data-value='browser']", function(e) {
        $("#landing").hide();
        $("#about").hide();
        $("#browser").show();
    });
    
    // Custom styling for pagination buttons
    $(".page-link").css("cursor", "pointer");
});

// Error handling for FASTA download
$(document).on("shiny:error", function(event) {
    if (event.error && event.error.message && event.error.message.includes("No proteomes selected")) {
        alert("Error: " + event.error.message);
    } else if (event.error && event.error.message) {
        alert("Error during FASTA download:\n" + event.error.message);
    }
});

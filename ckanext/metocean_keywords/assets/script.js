c]kan.module("metocean_keywords-module", function ($, _) {
  "use strict";
  return {
    options: {
      debug: false,
    },

    initialize: function () {
      $('#dataset-meta').click(function(e) {
        e.preventDefault();
        $(this).tab('show');
      });
      $('#dataset-meta-pane').show();

      /* highlight any ancestor elements in the GCMD keyword hierarchy
       * when hovered over */
      $('ul.tree').find('a.tag').hover(
                  function() { $(this).parentsUntil('ul.tree', 'ul').prev().
                                          addClass('highlight-ancestor') },
                  function() { $(this).parentsUntil('ul.tree', 'ul').prev().
                                          removeClass('highlight-ancestor') });
    }
  }
});

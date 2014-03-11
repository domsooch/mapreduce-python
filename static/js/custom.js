/*
Copyright 2014 Google Inc. All rights reserved.

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
*/

$(function() {
    $.validator.addMethod(
        "end_greater_than_start",
        function(value, element) {
            return parseInt($('#sequenceEnd').val()) >= parseInt($('#sequenceStart').val())
        },
        "End must be greater than or equal to start.");
    $.validator.addMethod(
        "start_less_than_end",
        function(value, element) {
            return parseInt($('#sequenceStart').val()) <= parseInt($('#sequenceEnd').val())
        },
        "Start must be less than or equal to end.");
    $.validator.addMethod(
        "start_greater_than_zero",
        function(value, element) {
            return parseInt($('#sequenceStart').val()) > 0
        },
        "Start must be greater than 0.");
    $("#coverageForm").validate({
        rules: {
            readsetId: "required",
            sequenceStart: {
                required: true,
                number: true,
                start_greater_than_zero: true,
                start_less_than_end: true
            },
            sequenceEnd: {
                required: true,
                number: true,
                end_greater_than_start: true
            }
        },
        messages: {
            readsetId: "Please provide a Readset Id.",
            sequenceStart: {
                required: "Please provide a Sequence Start."
            },
            sequenceStart: {
                required: "Please provide a Sequence End."
            }
         },
        submitHandler: function(form) {
            $('#coverageResults').hide();
            $('#progress').show();
            form.submit();
        }
    });
});

module seven_segment(
    input  wire [3:0] val,
    output reg  [6:0] display
);
    always_comb begin
        case (val)
            4'h0: display = 7'b1000000;  // 0
            4'h1: display = 7'b1111001;  // 1
            4'h2: display = 7'b0100100;  // 2
            4'h3: display = 7'b0110000;  // 3
            4'h4: display = 7'b0011001;  // 4
            4'h5: display = 7'b0010010;  // 5
            4'h6: display = 7'b0000010;  // 6
            4'h7: display = 7'b1111000;  // 7
            4'h8: display = 7'b0000000;  // 8
            4'h9: display = 7'b0010000;  // 9
            4'ha: display = 7'b0001000;  // a
            4'hb: display = 7'b0000011;  // b
            4'hc: display = 7'b1000110;  // c
            4'hd: display = 7'b0100001;  // d
            4'he: display = 7'b0000110;  // e
            4'hf: display = 7'b0001110;  // f

            default: display = 7'b1111111; // all off
        endcase
    end
endmodule
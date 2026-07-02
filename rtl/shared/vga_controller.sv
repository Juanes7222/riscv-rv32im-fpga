module vga_controller_1280x720 (
  input  logic clk,
  input  logic reset,
  output logic hsync,
  output logic vsync,
  output logic [10:0] hcount,
  output logic [9:0] vcount,
  output logic video_on
);

  localparam int HORIZONTAL_VISIBLE_AREA = 1280;
  localparam int HORIZONTAL_FRONT_PORCH = 110;
  localparam int HORIZONTAL_SYNC_PULSE = 40;
  localparam int HORIZONTAL_BACK_PORCH = 20;
  localparam int HORIZONTAL_TOTAL = HORIZONTAL_VISIBLE_AREA + HORIZONTAL_FRONT_PORCH + HORIZONTAL_SYNC_PULSE + HORIZONTAL_BACK_PORCH;

  localparam int VERTICAL_VISIBLE_AREA = 720;
  localparam int VERTICAL_FRONT_PORCH = 5;
  localparam int VERTICAL_SYNC_PULSE = 5;
  localparam int VERTICAL_BACK_PORCH = 20;
  localparam int VERTICAL_TOTAL = VERTICAL_VISIBLE_AREA + VERTICAL_FRONT_PORCH + VERTICAL_SYNC_PULSE + VERTICAL_BACK_PORCH;

  always_ff @(posedge clk or posedge reset) begin
    if (reset) begin
      hcount <= '0;
      vcount <= '0;
    end else begin
      if (hcount == (HORIZONTAL_TOTAL - 1)) begin
        hcount <= '0;
        
        if (vcount == (VERTICAL_TOTAL - 1)) begin
          vcount <= '0;
        end else begin
          vcount <= vcount + 1;
        end
      end else begin
        hcount <= hcount + 1;
      end
    end
  end

  assign hsync = (hcount >= (HORIZONTAL_VISIBLE_AREA + HORIZONTAL_FRONT_PORCH)) && 
                 (hcount < (HORIZONTAL_VISIBLE_AREA + HORIZONTAL_FRONT_PORCH + HORIZONTAL_SYNC_PULSE));

  assign vsync = (vcount >= (VERTICAL_VISIBLE_AREA + VERTICAL_FRONT_PORCH)) && 
                 (vcount < (VERTICAL_VISIBLE_AREA + VERTICAL_FRONT_PORCH + VERTICAL_SYNC_PULSE));

  assign video_on = (hcount < HORIZONTAL_VISIBLE_AREA) && (vcount < VERTICAL_VISIBLE_AREA);

endmodule